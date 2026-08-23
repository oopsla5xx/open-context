"""
Open:Context — Phase 4b architecture discovery (Rails HMVC only, this round).

Discovers the REAL component chain of a Rails-family app by scanning which
directories actually exist under app/ and which classes actually reference
which other classes — not a fixed 5-step chain assumed up front. A repo like
qlear-v2-admin uses `admin -> operation -> form -> model` (ActiveAdmin entry,
no serializer); a fixed-archetype guess would get that wrong.

AST-lite / regex pattern matching, no AST engine — same "don't over-engineer"
posture as validator.py's 6 HMVC rules. This module answers ONE question:
"what does the call-evidence in this codebase actually show?" It does NOT:
  - decide what SHOULD be forbidden (forbidden_dependencies) — that is a
    design-intent judgment call left to the LLM step in /oc-setup.
  - merge/aggregate multiple ecosystems in one scan — same non-recursive
    posture as discovery.py, scoped to one app/ tree per call.
  - propose a UX for presenting this to the user — that is deliberately
    deferred until this module has been run against real repos and the
    actual shape of the evidence (clean vs messy, clustered vs scattered
    outliers, typical component count) can inform the design instead of
    a guessed-at illustration.

Call-evidence heuristic: for component A's class tokens (camelized .rb file
basenames) to be counted as "A depends on B", a file in B's source must
reference one of A's tokens followed by a `.method_name` call — deliberately
broad (not just `.new`/`.call`) because Rails model usage varies widely
(`.find`, `.where`, `.create!`, `.with_lock`, ...). This is a known source of
false positives (e.g. a class token that collides with an unrelated method
receiver) — not filtered here; call-evidence output is meant to be reviewed,
not blindly trusted.

Confidence formula (edge-level): matched_files / total_files_in_from_component,
capped at 0.95. This is a first-pass formula, not a final calibration — expect
to revisit once real output shows whether hit rates cluster near 0/1 (clean
signal) or spread out (messy, needs a different formula).
"""
from __future__ import annotations

import re
from pathlib import Path

_NON_CODE_DIRS = {"assets", "views", "javascript"}


def _camelize(basename: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in basename.split("_") if part)


def discover_components(app_dir: Path) -> tuple[dict[str, list[Path]], set[str]]:
    """Directories directly under app_dir containing .rb files, recursively.
    Skips non-code dirs (assets/views/javascript). A symlinked directory (e.g.
    a `shared/` submodule mount, common in the qlear-v2-* family) is still
    scanned — its code is real and call-evidence into/out of it is real — but
    its name is returned in the second set so callers can flag it as external
    to this repo's own boundary rather than silently treating it as owned
    code. (qlear-v2-bot's own app/ has almost nothing but a symlinked
    `models`/`jobs`/etc — excluding those entirely produced a near-empty,
    unhelpful result; including them with an explicit external flag keeps the
    real signal without pretending shared/ is this repo's own code.)"""
    components: dict[str, list[Path]] = {}
    external: set[str] = set()
    if not app_dir.is_dir():
        return components, external
    for entry in sorted(app_dir.iterdir()):
        if not entry.is_dir() or entry.name in _NON_CODE_DIRS:
            continue
        rb_files = sorted(entry.rglob("*.rb"))
        if rb_files:
            components[entry.name] = rb_files
            if entry.is_symlink():
                external.add(entry.name)
    return components, external


def component_class_tokens(files: list[Path]) -> dict[str, Path]:
    """Camelized file basename -> defining file, but ONLY for files that actually
    declare a `class`/`module` matching that name somewhere in their content.

    File-basename-equals-class-name holds for ordinary Rails naming (operations,
    forms, models, controllers) but NOT for ActiveAdmin resource-registration
    files: `app/admin/company_domain.rb` contains `ActiveAdmin.register
    CompanyDomain do ... end`, not `class CompanyDomain` — and it happens to
    share its exact basename with the real `app/models/company_domain.rb`
    model. Without this check, the admin file's phantom "CompanyDomain" token
    collides with the model's real one, misattributing model call-evidence to
    the admin component (confirmed on qlear-v2-admin's operations/admin edge)."""
    tokens: dict[str, Path] = {}
    for f in files:
        token = _camelize(f.stem)
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(rf"^\s*(?:class|module)\s+(?:\w+::)*{re.escape(token)}\b", text, re.M):
            tokens[token] = f
    return tokens


_CALL_SUFFIX = r"\s*\.\s*[a-z_]\w*"


def _validator_shorthand_key(token: str) -> "str | None":
    """"PhoneNumberValidator" -> "phone_number" — Rails resolves a custom
    validator via `validates :field, phone_number: true` with no literal
    class-name reference anywhere in the calling file, so the plain
    `<Token>.<method>` pattern above can never see this usage. Without this,
    every custom Rails validator looks "unconnected" (confirmed on
    qlear-v2-admin: validators/ showed zero edges despite being used
    extensively by forms/ via this exact shorthand)."""
    suffix = "Validator"
    if not token.endswith(suffix) or token == suffix:
        return None
    base = token[: -len(suffix)]
    return re.sub(r"(?<!^)(?=[A-Z])", "_", base).lower()


def _token_patterns(token: str) -> list[re.Pattern]:
    patterns = [re.compile(rf"\b{re.escape(token)}\b{_CALL_SUFFIX}")]
    key = _validator_shorthand_key(token)
    if key:
        patterns.append(re.compile(rf"validates(?:_with)?\b[^\n]*\b{re.escape(key)}\s*:\s*(?:true|\{{)"))
        patterns.append(re.compile(rf"validates_with\s+[^\n]*\b{re.escape(token)}\b"))
    return patterns


def scan_call_evidence(components: dict[str, list[Path]]) -> list[dict]:
    """Directed call-evidence edges between components. Primarily regex hits
    of `<other component's class token>.<method>`, plus (for validator
    components specifically) Rails' implicit `validates :field, key: true`
    shorthand — see _validator_shorthand_key for why that carve-out exists."""
    tokens_by_component = {name: component_class_tokens(files) for name, files in components.items()}
    file_text_cache: dict[Path, list[str]] = {}

    def lines_of(f: Path) -> list[str]:
        if f not in file_text_cache:
            try:
                file_text_cache[f] = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                file_text_cache[f] = []
        return file_text_cache[f]

    edges = []
    for from_name, from_files in components.items():
        for to_name, to_tokens in tokens_by_component.items():
            if from_name == to_name or not to_tokens:
                continue
            token_patterns = [(token, pat) for token in to_tokens for pat in _token_patterns(token)]
            hits = []
            matched_files = set()
            for f in from_files:
                for lineno, line in enumerate(lines_of(f), 1):
                    for token, pat in token_patterns:
                        if pat.search(line):
                            hits.append({
                                "file": str(f), "line": lineno,
                                "token": token, "code": line.strip(),
                            })
                            matched_files.add(f)
                            break
            if hits:
                confidence = round(min(0.95, len(matched_files) / len(from_files)), 2)
                edges.append({
                    "from": from_name,
                    "to": to_name,
                    "matched_files": len(matched_files),
                    "total_files": len(from_files),
                    "confidence": confidence,
                    "hits": hits,
                })
    return edges


def _suggested_flow(edges: list[dict]) -> dict:
    """
    Topological order over every component that has at least one edge — NOT a
    single greedy walk. A single-path walk silently drops real fan-out (e.g.
    qlear-v2-admin's `operations` calls both `forms` (0.68 confidence) and
    `models` (0.91) — a greedy walk that always follows the highest-confidence
    edge would report `admin -> operations -> models` and drop `forms`
    entirely, even though the evidence for it is real and only somewhat
    weaker). Every connected component must appear in `flow`; a cycle is
    reported in `cycle_detected` rather than silently broken.
    """
    out_edges: dict[str, list[str]] = {}
    in_degree: dict[str, int] = {}
    confidence_of: dict[tuple[str, str], float] = {}
    for e in edges:
        out_edges.setdefault(e["from"], []).append(e["to"])
        in_degree[e["to"]] = in_degree.get(e["to"], 0) + 1
        in_degree.setdefault(e["from"], in_degree.get(e["from"], 0))
        confidence_of[(e["from"], e["to"])] = e["confidence"]

    connected = set(in_degree)
    if not connected:
        return {"flow": [], "cycle_detected": []}

    ready = [n for n in connected if in_degree[n] == 0]
    flow: list[str] = []
    visited: set[str] = set()
    while ready:
        ready.sort(key=lambda n: (-sum(confidence_of.get((n, t), 0) for t in out_edges.get(n, [])), n))
        node = ready.pop(0)
        if node in visited:
            continue
        flow.append(node)
        visited.add(node)
        for to in out_edges.get(node, []):
            if to in visited:
                continue
            in_degree[to] -= 1
            if in_degree[to] <= 0 and to not in ready:
                ready.append(to)

    cycle_nodes = sorted(connected - visited)
    flow.extend(cycle_nodes)  # never silently drop a component stuck in a cycle
    return {"flow": flow, "cycle_detected": cycle_nodes}


_CYCLE_RATIO_RED_FLAG = 0.5


def assess_confidence(result: dict) -> dict:
    """
    Whether to propose `suggested_flow` at all, as a small set of discrete,
    inspectable red flags rather than one blended numeric score.

    A blended score (weighted penalties for cycles/unconnected-ratio/entry-
    count/weak-edge-ratio) was tried and rejected: on qlear-v2-admin — a
    hand-verified-correct result — every weighting attempt landed around
    ~69%, just under a 70% propose threshold. The cause wasn't bad weights;
    it was conflating two different things into one number: real structural
    richness (3 legitimate entry points, some genuinely-rare peripheral
    edges) is not the same as detection uncertainty, and no single score
    can honestly represent both. Per-edge confidence (already in `edges`)
    is the trustworthy number; this function only gates the binary
    propose/don't-propose call using signals that are unambiguous on their
    own, mirroring the per-field (not blended) confidence decision in
    discovery.py (Phase 4a).

    Returns {"propose": bool, "reasons": [str, ...]} — reasons is empty
    when propose is True.
    """
    if not result.get("edges"):
        return {"propose": False, "reasons": ["no call-evidence found — nothing to propose"]}

    connected = {n for e in result["edges"] for n in (e["from"], e["to"])}
    cycle_nodes = set(result.get("cycle_detected", []))
    cycle_ratio = len(cycle_nodes) / len(connected) if connected else 0.0

    if cycle_ratio >= _CYCLE_RATIO_RED_FLAG:
        return {
            "propose": False,
            "reasons": [
                f"cycle covers {len(cycle_nodes)}/{len(connected)} connected components "
                f"({', '.join(sorted(cycle_nodes))}) — no reliable linear order to propose"
            ],
        }

    return {"propose": True, "reasons": []}


def discover_architecture(repo: "Path | str", app_subdir: str = "app") -> dict:
    """
    Returns:
      {
        "repo": str, "app_subdir": str,
        "components": { name: file_count },
        "edges": [ {from, to, matched_files, total_files, confidence, hits} ],
        "allowed_dependencies": { component_name: [to_component, ...] },
        "suggested_flow": [component_name, ...],
        "entry_candidates": [component_name, ...],   # zero incoming edges, has outgoing
        "terminal_candidates": [component_name, ...], # has incoming edges, zero outgoing
        "unconnected": [component_name, ...],          # no edges in or out at all
        "external_components": [component_name, ...], # symlinked (e.g. shared/ submodule) —
                                                        # real code, real edges, but not owned
                                                        # by this repo; caller decides whether
                                                        # to include in the final architecture.flow
      }
    """
    repo = Path(repo).resolve()
    app_dir = repo / app_subdir
    components, external_components = discover_components(app_dir)
    if not components:
        return {
            "repo": str(repo), "app_subdir": app_subdir, "components": {}, "edges": [],
            "allowed_dependencies": {}, "suggested_flow": [], "cycle_detected": [],
            "entry_candidates": [], "terminal_candidates": [], "unconnected": [],
            "external_components": [],
            "note": f"no component directories with .rb files found under {app_subdir}/",
        }

    edges = scan_call_evidence(components)

    allowed_dependencies: dict[str, list[str]] = {}
    for e in edges:
        allowed_dependencies.setdefault(e["from"], [])
        if e["to"] not in allowed_dependencies[e["from"]]:
            allowed_dependencies[e["from"]].append(e["to"])

    has_out = {e["from"] for e in edges}
    has_in = {e["to"] for e in edges}
    entry_candidates = sorted(has_out - has_in)
    terminal_candidates = sorted(has_in - has_out)
    unconnected = sorted(set(components) - has_out - has_in)
    flow_result = _suggested_flow(edges)

    return {
        "repo": str(repo),
        "app_subdir": app_subdir,
        "components": {name: len(files) for name, files in components.items()},
        "edges": edges,
        "allowed_dependencies": allowed_dependencies,
        "suggested_flow": flow_result["flow"],
        "cycle_detected": flow_result["cycle_detected"],
        "entry_candidates": entry_candidates,
        "terminal_candidates": terminal_candidates,
        "unconnected": unconnected,
        "external_components": sorted(external_components),
    }
