"""
Open:Context Validator — two independent validators:

  1. Phrasing coverage  — run phrasing test files against the resolver and
                          check amplification risk in the context model.
  2. Architecture rules — static analysis of Rails HMVC compliance (6 rules).

All functions return plain dicts/lists — no argparse, no print, no sys.exit.
The CLI layer (cli.py) handles formatting and exit codes.
"""

import re
from pathlib import Path

from .resolver import resolve


# ─────────────────────────────────────────────────────────────────────────────
# Phrasing coverage validator
# ─────────────────────────────────────────────────────────────────────────────

AMPLIFICATION_DANGER = 4
AMPLIFICATION_NOTE = 3


def load_phrasings(tests_dir: "Path | str", domain: str) -> list[tuple[str, str]]:
    """
    Load phrasing test pairs from <tests_dir>/<domain>.txt.
    Returns list of (phrasing, expected_domain) tuples.
    Lines starting with # are comments. Blank lines are skipped.
    """
    path = Path(tests_dir) / f"{domain}.txt"
    if not path.exists():
        return []
    pairs = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            continue
        phrasing, expected = line.split("|", 1)
        pairs.append((phrasing.strip(), expected.strip()))
    return pairs


def run_phrasing_tests(ctx: dict, tests_dir: "Path | str") -> dict:
    """
    Run phrasing tests for all domains defined in ctx.
    Returns:
      {
        "by_domain": { domain_name: { tested, correct, pct, risk, failures } },
        "total_tested": int,
        "total_correct": int,
        "total_pct": float,
      }
    """
    domain_names = [d["name"] for d in ctx.get("domains", [])]
    results = {}
    total_tested = total_correct = 0

    for domain in domain_names:
        pairs = load_phrasings(tests_dir, domain)
        tested = len(pairs)
        correct = 0
        failures = []

        for phrase, expected in pairs:
            result = resolve(phrase, context=ctx)
            matched = [d["name"] for d in result["matched_domains"]]
            if expected in matched:
                correct += 1
            else:
                failures.append({"phrase": phrase, "expected": expected, "got": matched})

        pct = (correct / tested * 100) if tested > 0 else 0.0
        risk = _risk_label(pct) if tested > 0 else "UNTESTED"
        results[domain] = {
            "tested": tested,
            "correct": correct,
            "pct": pct,
            "risk": risk,
            "failures": failures,
        }
        total_tested += tested
        total_correct += correct

    return {
        "by_domain": results,
        "total_tested": total_tested,
        "total_correct": total_correct,
        "total_pct": (total_correct / total_tested * 100) if total_tested > 0 else 0.0,
    }


def _risk_label(pct: float) -> str:
    if pct < 50:
        return "HIGH"
    if pct < 80:
        return "MEDIUM"
    return "LOW"


def _find_shared_root_pairs(keywords: list[str]) -> list[tuple[str, str, str]]:
    pairs = []
    seen = set()
    for i, kw1 in enumerate(keywords):
        parts1 = set(kw1.split("_"))
        for j, kw2 in enumerate(keywords):
            if i == j:
                continue
            parts2 = set(kw2.split("_"))
            shared = parts1 & parts2
            prefix = kw1.startswith(kw2) or kw2.startswith(kw1)
            if shared or prefix:
                key = tuple(sorted([kw1, kw2]))
                if key not in seen:
                    seen.add(key)
                    root = min(shared, key=len) if shared else min(kw1, kw2, key=len)
                    pairs.append((kw1, kw2, root))
    return pairs


def run_amplification_checks(ctx: dict) -> list[dict]:
    """
    Check for amplification risk: single tokens matching multiple keywords in
    the same domain raise the threshold and may block legitimate co-routing.
    Returns list of findings with level "WARNING" or "NOTE".
    """
    findings = []
    for domain in ctx.get("domains", []):
        kws = domain.get("keywords", [])
        seen_roots = set()
        for kw1, kw2, root in _find_shared_root_pairs(kws):
            if root in seen_roots:
                continue
            seen_roots.add(root)
            result = resolve(root, context=ctx)
            score = next(
                (d["score"] for d in result["matched_domains"] if d["name"] == domain["name"]),
                0,
            )
            if score >= AMPLIFICATION_NOTE:
                level = "WARNING" if score >= AMPLIFICATION_DANGER else "NOTE"
                findings.append({
                    "domain": domain["name"],
                    "root_token": root,
                    "shared_keywords": [kw1, kw2],
                    "score": score,
                    "level": level,
                    "detail": (
                        f"Token '{root}' matches {score} keywords in {domain['name']} "
                        f"({kw1}, {kw2}, ...). "
                        + ("Threshold may block co-routing." if level == "WARNING" else "Monitor.")
                    ),
                })
    return findings


# ─────────────────────────────────────────────────────────────────────────────
# Architecture rules (6 HMVC compliance checks)
# ─────────────────────────────────────────────────────────────────────────────

# R1 — classes that may legitimately appear in controller files with method calls.
# Add project-specific classes to this list as needed (e.g. your JWT module,
# custom exception base, or shared library namespaces).
_R1_ALLOWED_CLASSES = re.compile(
    r"Serializer|Operation|Form|Policy|Settings|ActiveModel|ActiveRecord|"
    r"ActionController|V1::|I18n"
)

_R1_AR_PATTERN = re.compile(
    r"\b[A-Z][a-zA-Z]+\.(where|find_by[!]?|create[!]?|save[!]?|destroy)\s*\("
)

# R3 — Form.new(params without permit_params
_R3_PATTERN = re.compile(r"Form\.new\(\s*params[^_\.]")

# R4 — render json: directly
_R4_PATTERN = re.compile(r"render\s+json:")

# R5 — Unscoped class.find(params[:id]) in operations.
# Global models (shared infrastructure not scoped per tenant) are excluded.
# Extend this list based on your project's actual global models.
# Each entry must be confirmed: the model is genuinely shared across all tenants.
_R5_GLOBAL_MODELS = re.compile(
    r"^(?:Component|Template|Industry|Settings|SessionToken|AnonymousUser)\b"
)
_R5_PATTERN = re.compile(
    r"(?:^|[\s(=,;])([A-Z][a-zA-Z]+)\.find\s*\(\s*params\[:id\]"
)

# R6 — bare raise (string literal or standard Ruby exception class)
_R6_PATTERN = re.compile(
    r'\braise\s+(?:["\']|StandardError\b|RuntimeError\b|ArgumentError\b|TypeError\b)'
)


def _r1_check(filepath: Path, content: str) -> list[dict]:
    violations = []
    for i, line in enumerate(content.splitlines(), 1):
        s = line.strip()
        if s.startswith("#"):
            continue
        if _R1_AR_PATTERN.search(s) and not _R1_ALLOWED_CLASSES.search(s):
            violations.append({"line": i, "code": line.rstrip(), "detail": "AR query in controller"})
        elif re.search(r"\braise\b", s) and not s.startswith("rescue"):
            violations.append({"line": i, "code": line.rstrip(), "detail": "raise statement in controller"})
    return violations


def _r2_check(filepath: Path, content: str) -> list[dict]:
    if "Form.new(" in content and ".valid!" not in content:
        return [{"line": None, "code": None,
                 "detail": "Form.new() present but .valid! not called anywhere in file"}]
    return []


def _r3_check(filepath: Path, content: str) -> list[dict]:
    violations = []
    for i, line in enumerate(content.splitlines(), 1):
        s = line.strip()
        if s.startswith("#"):
            continue
        if _R3_PATTERN.search(s):
            violations.append({"line": i, "code": line.rstrip(),
                                "detail": "Form.new(params) instead of Form.new(permit_params)"})
    return violations


def _r4_check(filepath: Path, content: str) -> list[dict]:
    violations = []
    for i, line in enumerate(content.splitlines(), 1):
        s = line.strip()
        if s.startswith("#"):
            continue
        if _R4_PATTERN.search(s):
            violations.append({"line": i, "code": line.rstrip(),
                                "detail": "Direct render json: — use render_json() or render_error()"})
    return violations


def _r5_check(filepath: Path, content: str) -> list[dict]:
    violations = []
    for i, line in enumerate(content.splitlines(), 1):
        s = line.strip()
        if s.startswith("#"):
            continue
        m = _R5_PATTERN.search(s)
        if m:
            class_name = m.group(1)
            if not _R5_GLOBAL_MODELS.match(class_name):
                violations.append({
                    "line": i,
                    "code": line.rstrip(),
                    "detail": (
                        f"Unscoped {class_name}.find(params[:id]) — "
                        f"verify this is safe or scope via your multi-tenancy association"
                    ),
                })
    return violations


def _r6_check(filepath: Path, content: str) -> list[dict]:
    violations = []
    for i, line in enumerate(content.splitlines(), 1):
        s = line.strip()
        if s.startswith("#"):
            continue
        if _R6_PATTERN.search(s):
            violations.append({"line": i, "code": line.rstrip(),
                                "detail": "Bare raise — use your project's custom exception subclass"})
    return violations


# Rule registry
ARCH_RULES = [
    {
        "id": "R1",
        "name": "No business logic in controller",
        "description": "Controllers must delegate to Operations — no AR queries or raises in action methods.",
        "glob": "app/controllers/v1/**/*_controller.rb",
        "check": _r1_check,
    },
    {
        "id": "R2",
        "name": "form.valid! before mutations",
        "description": "Operations that instantiate a Form must call .valid! to validate before mutating.",
        "glob": "app/operations/v1/**/*_operation.rb",
        "check": _r2_check,
    },
    {
        "id": "R3",
        "name": "permit_params safety",
        "description": "Forms must be instantiated with permit_params, not raw params.",
        "glob": "app/operations/v1/**/*_operation.rb",
        "check": _r3_check,
    },
    {
        "id": "R4",
        "name": "render_json/render_error only",
        "description": "Controllers must use render_json() or render_error(), never render json: directly.",
        "glob": "app/controllers/v1/**/*_controller.rb",
        "check": _r4_check,
    },
    {
        "id": "R5",
        "name": "Scoped resource lookup",
        "description": "Operations must not use unscoped class.find(params[:id]) for tenant-scoped resources.",
        "glob": "app/operations/v1/**/*_operation.rb",
        "check": _r5_check,
    },
    {
        "id": "R6",
        "name": "Custom exception classes only",
        "description": "Operations must signal failures with project-specific exception subclasses, not bare raises.",
        "glob": "app/operations/v1/**/*_operation.rb",
        "check": _r6_check,
    },
]


def collect_files(base: Path, glob: str, path_filter: "Path | None") -> list[Path]:
    """Collect files matching glob under base, optionally filtered to path_filter subtree."""
    files = sorted(base.glob(glob))
    if path_filter:
        pf = path_filter.resolve()
        files = [f for f in files if pf in f.resolve().parents or f.resolve() == pf]
    return files


def run_arch_validate(base: Path, path_filter: "Path | None" = None) -> dict:
    """
    Run all 6 HMVC architecture rules against the codebase at `base`.
    Returns:
      {
        "scope": str,
        "total_violations": int,
        "total_files_checked": int,
        "results": [ { rule, files_checked, violations } ]
      }
    """
    all_results = []
    total_violations = 0
    total_files_checked = 0

    for rule in ARCH_RULES:
        files = collect_files(base, rule["glob"], path_filter)
        rule_violations = []

        for filepath in files:
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            total_files_checked += 1
            hits = rule["check"](filepath, content)
            if hits:
                rel = filepath.relative_to(base)
                rule_violations.append({"file": str(rel), "hits": hits})

        total_violations += sum(len(rv["hits"]) for rv in rule_violations)
        all_results.append({
            "rule": rule,
            "files_checked": len(files),
            "violations": rule_violations,
        })

    return {
        "scope": str(path_filter or base),
        "total_violations": total_violations,
        "total_files_checked": total_files_checked,
        "results": all_results,
    }
