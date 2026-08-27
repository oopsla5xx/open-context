#!/usr/bin/env python3
"""
Context Resolver v0 — Open:Context

Resolution strategy (no LLM, no vectors, no embeddings):
  1. Keyword matching against domain definitions in context.yaml
  2. Actor inference from domain metadata
  3. Action inference from task verb
  4. Component chain traversal (chain declared in context.yaml, not hardcoded)
  5. File inference from domain.related_components + naming conventions
  6. Rule selection by domain + severity

The resolver is generic — it does NOT contain task-specific or framework-specific
logic. Resolution is driven entirely by context.yaml metadata.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

# Verb → CRUD action inference table
ACTION_VERBS = {
    # create-family
    "implement": "create", "create":  "create", "add":    "create",
    "build":     "create", "make":    "create", "write":  "create",
    "register":  "create", "send":    "create", "invite": "create",
    "request":   "create", "submit":  "create", "post":   "create",
    "exchange":  "create", "redeem":  "create", "claim":  "create",
    "use":       "create", "enable":  "create", "allow":  "create",
    "issue":     "create",
    "reset":     "create",
    # update-family
    "update":    "update", "edit":    "update", "modify": "update",
    "change":    "update", "patch":   "update",
    # destroy-family
    "delete":    "destroy", "remove": "destroy", "cancel": "destroy",
    "destroy":   "destroy", "revoke": "destroy",
    # read-family
    "list":      "index",   "index":  "index",  "search": "index",
    "filter":    "index",
    "show":      "show",    "get":    "show",   "fetch":  "show",
    "find":      "show",    "view":   "show",   "check":  "show",
    "verify":    "show",    "read":   "show",
}

# Generic task-level stop words (not Ruby keywords)
STOP_WORDS = {
    "a", "an", "the", "and", "or", "for", "in", "to", "of", "with", "by",
    "at", "from", "that", "this", "it", "is", "are", "was", "were", "be",
    "been", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "shall", "api", "endpoint",
    "feature", "functionality", "so", "as", "on", "up", "out", "about",
    "their", "they", "them", "user", "users",
}


# ─────────────────────────────────────────────────────────────────────────────
# Core resolution helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_context(path: "Path | str") -> dict:
    """Load context.yaml from the given path."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def tokenize(text: str) -> list[str]:
    """Lowercase + split on non-alphanumeric + remove stop words."""
    raw = re.findall(r"[a-z][a-z0-9]*", text.lower())
    return [t for t in raw if t not in STOP_WORDS and len(t) > 1]


def infer_action(text: str) -> str:
    """Return the CRUD action implied by the first recognized verb in the text."""
    for word in re.findall(r"[a-z]+", text.lower()):
        if word in ACTION_VERBS:
            return ACTION_VERBS[word]
    return "create"  # default: most tasks ask to implement / add something


def _singularize(word: str) -> str:
    """Naive singularization so 'company' also matches token 'companies'."""
    if word.endswith("ies") and len(word) > 3:
        return word[:-3] + "y"
    if word.endswith(("ses", "xes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 1:
        return word[:-1]
    return word


def _token_matches_word(token: str, word: str) -> bool:
    """
    Exact match, or same after singularizing, always count.
    Prefix match (either direction) only counts for tokens of length >= 3 —
    a 2-letter token (e.g. 'me') is coincidental noise as a prefix of an
    unrelated longer word (e.g. 'member'), not real evidence of intent.
    """
    if token == word or _singularize(token) == _singularize(word):
        return True
    if len(token) < 3:
        return False
    return word.startswith(token) or token.startswith(word)


def score_domain(domain: dict, tokens: list[str]) -> tuple[int, list[str]]:
    """
    Match domain keywords against task tokens.

    Single-word keywords match if any task token equals, prefixes, or
    singularizes to the same form as the keyword.

    Underscore-joined compound keywords (e.g. 'company_member') score one
    point PER distinct part found among the tokens, not one point for the
    whole keyword — a keyword whose parts individually appear as tokens
    ("company" AND "member" both present) is real evidence of two matched
    concepts, not one. Scoring it as 1 would unfairly discard domains that
    happen to only have compound keywords vs. domains that accumulate score
    from several unrelated single-word keywords.

    Returns (score, matched_keyword_list) — matched_keyword_list still lists
    each matched keyword once, for display/reason purposes.
    """
    matched = []
    score = 0

    for kw in domain.get("keywords", []):
        kw_parts = kw.split("_")
        if len(kw_parts) == 1:
            contribution = 1 if any(_token_matches_word(t, kw) for t in tokens) else 0
        else:
            contribution = sum(
                1 for part in set(kw_parts)
                if any(_token_matches_word(t, part) for t in tokens)
            )

        if contribution > 0:
            matched.append(kw)
            score += contribution

    return score, matched


def match_subtypes(domains: list[dict], tokens: list[str]) -> list[dict]:
    """
    For each matched domain that has a 'subtypes' list, find the best-matching
    subtype using the same keyword scoring as domain matching.

    Returns a list of dicts — one per domain that has a matched subtype:
      { "subtype": <subtype dict>, "parent_domain": str, "score": int,
        "matched_keywords": list[str] }

    Falls back gracefully when a domain has no subtypes defined.
    This is a generic mechanism — works for any domain with subtypes in the
    context model.
    """
    result = []
    for domain in domains:
        subtypes = domain.get("subtypes", [])
        if not subtypes:
            continue
        scored = []
        for st in subtypes:
            score, kws = score_domain(st, tokens)
            if score > 0:
                scored.append((score, st, kws))
        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            best_score, best_st, best_kws = scored[0]
            result.append({
                "subtype":          best_st,
                "parent_domain":    domain["name"],
                "score":            best_score,
                "matched_keywords": best_kws,
            })
    return result


def select_rules(context: dict, domain_names: set[str]) -> list[dict]:
    """
    Select applicable rules.
    - Rules with a domain filter: only included when the domain matches.
    - Rules without a domain filter (general architecture rules): always included.
    """
    results = []
    for rule in context.get("rules", []):
        rule_domains = set(rule.get("domain", []))
        if rule_domains and not rule_domains.intersection(domain_names):
            continue
        results.append(rule)
    return results


def _directory_naming_hint(file_patterns: dict, action: str) -> str:
    """
    Build a naming hint for a directory-type related_component from this
    project's own context.yaml `files.<component>.naming` templates —
    never a hardcoded framework-specific extension. Only templates that
    are action-based (contain '{action}') apply to a directory fallback;
    resource-based naming (e.g. a controller's '{resource}_controller.rb')
    doesn't describe what to look for inside an unlisted directory.
    """
    hints = [
        naming.replace("{action}", action)
        for comp_def in file_patterns.values()
        if "{action}" in (naming := comp_def.get("naming", ""))
    ]
    return " / ".join(hints) if hints else f"{action}_*"


def resolve_files(
    domains: list[dict],
    action: str,
    tokens: list[str],
    matched_subtypes: list[dict] | None = None,
    file_patterns: dict | None = None,
) -> list[dict]:
    """
    Infer relevant files from domain.related_components and, when present,
    from the matched subtype's related_components (more specific).

    Resolution priority:
      1. Subtype-level components — used when a subtype matched (specific files
         and narrowed directories). Replaces the domain-level directory pointers.
      2. Domain-level specific files (.rb) — always included even when subtypes
         matched, because they are shared infrastructure.
      3. Domain-level directory pointers — only included as fallback when NO
         subtype was matched.
    """
    files: list[dict] = []
    seen: set[str] = set()
    naming_hint = _directory_naming_hint(file_patterns or {}, action)

    if matched_subtypes:
        for si in matched_subtypes:
            st = si["subtype"]
            for component in st.get("related_components", []):
                if component in seen:
                    continue
                seen.add(component)
                p = Path(component)
                if p.suffix:
                    files.append({
                        "path": component,
                        "type": "specific_file",
                        "reason": (
                            f"Subtype '{st['name']}' (under {si['parent_domain']}) — "
                            f"narrowed from domain to this specific subtype."
                        ),
                    })
                else:
                    files.append({
                        "path": component,
                        "type": "search_directory",
                        "naming_hint": naming_hint,
                        "reason": (
                            f"Subtype '{st['name']}' directory. "
                            f"Look for '{naming_hint}' — "
                            f"keywords: {', '.join(tokens[:6])}."
                        ),
                    })

    for domain in domains:
        for component in domain.get("related_components", []):
            if component in seen:
                continue
            p = Path(component)
            is_specific_file = bool(p.suffix)

            if is_specific_file:
                seen.add(component)
                files.append({
                    "path": component,
                    "type": "specific_file",
                    "reason": (
                        f"Explicitly listed in domain '{domain['name']}' — "
                        f"directly relevant to this task."
                    ),
                })
            elif not matched_subtypes:
                seen.add(component)
                files.append({
                    "path": component,
                    "type": "search_directory",
                    "naming_hint": naming_hint,
                    "reason": (
                        f"Domain '{domain['name']}' related directory. "
                        f"Look for '{naming_hint}' files — "
                        f"task keywords to guide search: {', '.join(tokens[:6])}."
                    ),
                })

    return files


def domains_by_path(context: dict, rel_path: str) -> list[dict]:
    """
    Reverse lookup: which domains claim rel_path via their domain-level
    related_components (exact file match, or the path falling under a
    declared directory)? rel_path must already be relative to repo root,
    using '/' separators.

    Subtype-level related_components are deliberately not considered here —
    subtypes are disambiguated by scoring task-text keywords (see
    match_subtypes()), and a bare file path carries no task text to score
    against. Domain-level matching is the only signal available.

    Returns every domain that matches — callers should not assume a single
    "correct" domain when multiple domains declare overlapping paths.
    """
    rel_path = rel_path.replace("\\", "/").lstrip("/")
    matches = []
    for domain in context.get("domains", []):
        for component in domain.get("related_components", []):
            comp = component.replace("\\", "/").lstrip("/")
            if Path(comp).suffix:
                if rel_path == comp:
                    matches.append(domain)
                    break
            else:
                comp_dir = comp.rstrip("/")
                if rel_path == comp_dir or rel_path.startswith(comp_dir + "/"):
                    matches.append(domain)
                    break
    return matches


def format_drift_report(rel_path: str, domains: list[dict], rules: list[dict]) -> str:
    """
    Lightweight report for the PreToolUse domain-drift hook: rules +
    patterns only for the newly-surfaced domains.

    Deliberately omits ACTION/ACTOR/COMPONENTS — those are inferred from
    task text in resolve()/format_report(), and this hook only has a file
    path, not a task string, so there is nothing real to infer them from.
    """
    lines: list[str] = []
    sep = "─" * 70
    domain_names = ", ".join(d["name"] for d in domains)

    lines += [
        sep,
        f"[open-context] DOMAIN DRIFT — {rel_path}",
        f"DOMAINS : {domain_names} (not yet surfaced this turn)",
        sep,
    ]

    lines.append(f"\n[RULES]  ({len(rules)} applicable)")
    for rule in rules:
        lines.append(f"  [{rule.get('severity', 'minor').upper():<8}] {rule['id']}")
        lines.append(f"             {rule['description'][:70]}")
        if rule.get("guidance"):
            lines.append("             [GUIDANCE]")
            for gl in rule["guidance"].strip().split("\n"):
                lines.append(f"               {gl}")

    patterns: list[dict] = []
    seen_ids: set[str] = set()
    for d in domains:
        for p in d.get("patterns", []):
            if p["id"] not in seen_ids:
                seen_ids.add(p["id"])
                patterns.append(p)

    if patterns:
        lines.append(f"\n[PATTERNS]  ({len(patterns)} applicable)")
        for p in patterns:
            lines.append(f"\n  [{p['id']}]")
            desc = " ".join(p["description"].strip().split())
            for chunk in [desc[i:i + 68] for i in range(0, len(desc), 68)]:
                lines.append(f"    {chunk}")

    lines.append("\n" + sep)
    return "\n".join(lines)


def component_reason(comp: str, components: dict) -> str:
    """
    Human-readable explanation for why this component layer is included.

    Derived entirely from context.yaml's components.<comp> block
    (responsibility + patterns) — no framework-specific text is hardcoded
    here, so the same function works for any architecture.flow a project
    declares, not just Rails HMVC component names.
    """
    comp_def = components.get(comp) or {}
    parts: list[str] = []

    responsibilities = comp_def.get("responsibility", [])
    if responsibilities:
        parts.append(f"Responsibilities: {', '.join(responsibilities)}.")

    pattern_descs = [
        p["description"].strip().rstrip(".") + "."
        for p in comp_def.get("patterns", [])
        if p.get("description")
    ]
    if pattern_descs:
        parts.append(" ".join(pattern_descs[:2]))

    if parts:
        return " ".join(parts)

    return f"'{comp}' is part of the architecture flow for this task."


# ─────────────────────────────────────────────────────────────────────────────
# Main resolver
# ─────────────────────────────────────────────────────────────────────────────

def resolve(task: str, context: dict, *, include_all_domains: bool = False) -> dict:
    """
    Resolve a task string into relevant context: components, rules, files.
    context: pre-loaded YAML dict from load_context().
    include_all_domains: skip threshold filtering and include every domain
    (used to compute the full-context baseline for token savings stats).
    Note: zero-score domains are still passed through subtype/rule resolution,
    so the baseline may include subtype-level content for irrelevant domains.
    """
    tokens = tokenize(task)
    action = infer_action(task)

    # ── 1. Domain matching ───────────────────────────────────────────────────
    scored: list[tuple[int, dict, list[str]]] = []
    for domain in context.get("domains", []):
        score, matched_kws = score_domain(domain, tokens)
        if include_all_domains or score > 0:
            scored.append((score, domain, matched_kws))
    scored.sort(key=lambda x: x[0], reverse=True)

    if not include_all_domains:
        # Threshold: only keep domains whose score >= 66% of the top score,
        # with a minimum absolute score of 2.
        top_score = scored[0][0] if scored else 0
        threshold = max(2, top_score * 0.66)
        scored = [(s, d, kws) for s, d, kws in scored if s >= threshold]

    matched_domains: list[dict] = [d for _, d, _ in scored]
    match_info: list[dict] = [
        {
            "name":             d["name"],
            "score":            s,
            "matched_keywords": kws,
            "typical_actors":   d.get("typical_actors", []),
        }
        for s, d, kws in scored
    ]

    # ── 1b. Subtype matching ─────────────────────────────────────────────────
    matched_subtypes = match_subtypes(matched_domains, tokens)
    subtype_info: list[dict] = [
        {
            "name":             si["subtype"]["name"],
            "parent_domain":    si["parent_domain"],
            "score":            si["score"],
            "matched_keywords": si["matched_keywords"],
        }
        for si in matched_subtypes
    ]

    # ── 2. Actor inference ───────────────────────────────────────────────────
    actors: list[str] = []
    for d in matched_domains:
        for actor in d.get("typical_actors", []):
            if actor not in actors:
                actors.append(actor)
    if not actors:
        default_actor = context.get("project", {}).get("default_actor", "user")
        actors = [default_actor]

    # ── 3. Component chain ───────────────────────────────────────────────────
    # architecture.flow is optional (a repo with no clear layered architecture
    # may omit it entirely) — degrades to an empty base chain, extended below
    # only by whatever extra_components matched domains declare.
    base_flow: list[str] = list(context.get("architecture", {}).get("flow", []) or [])
    domain_names: set[str] = {d["name"] for d in matched_domains}

    for d in matched_domains:
        for ec in d.get("extra_components", []):
            if ec not in base_flow:
                base_flow.append(ec)

    # ── 4. Rule selection ────────────────────────────────────────────────────
    applicable_rules = select_rules(context, domain_names)

    # ── 5. File inference ────────────────────────────────────────────────────
    files = resolve_files(
        matched_domains, action, tokens,
        matched_subtypes=matched_subtypes,
        file_patterns=context.get("files", {}),
    )

    # ── 6. Component reasons ─────────────────────────────────────────────────
    comp_reasons = {
        comp: component_reason(comp, context.get("components", {}))
        for comp in base_flow
    }
    for d in matched_domains:
        for ec, reason in d.get("extra_component_reasons", {}).items():
            if ec in comp_reasons:
                comp_reasons[ec] = reason

    # ── 7. Domain/subtype patterns ───────────────────────────────────────────
    domain_patterns: list[dict] = []
    seen_pattern_ids: set[str] = set()
    for domain in matched_domains:
        for p in domain.get("patterns", []):
            if p["id"] not in seen_pattern_ids:
                seen_pattern_ids.add(p["id"])
                domain_patterns.append({
                    "id":          p["id"],
                    "description": p["description"],
                    "source":      f"domain:{domain['name']}",
                })
    for si in matched_subtypes:
        if si["score"] < 2:
            continue
        st = si["subtype"]
        for p in st.get("patterns", []):
            if p["id"] not in seen_pattern_ids:
                seen_pattern_ids.add(p["id"])
                domain_patterns.append({
                    "id":          p["id"],
                    "description": p["description"],
                    "source":      f"subtype:{st['name']}",
                })

    return {
        "task":              task,
        "tokens":            tokens,
        "action":            action,
        "matched_domains":   match_info,
        "matched_subtypes":  subtype_info,
        "actors":            actors,
        "components":        base_flow,
        "component_reasons": comp_reasons,
        "domain_patterns":   domain_patterns,
        "rules": [
            {
                "id":          r["id"],
                "description": r["description"],
                "severity":    r.get("severity", "minor"),
                "guidance":    r.get("guidance", ""),
            }
            for r in applicable_rules
        ],
        "files": files,
        "excluded": [
            "Full architecture documentation",
            "Unrelated domain rules",
            "Database schema",
            "Routing table",
            "Source code of uninvolved domains",
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Output formatter
# ─────────────────────────────────────────────────────────────────────────────

def format_report(r: dict) -> str:
    lines: list[str] = []
    sep = "─" * 70

    lines += [
        sep,
        f"TASK   : {r['task']}",
        f"TOKENS : {r['tokens']}",
        f"ACTION : {r['action']}",
        sep,
    ]

    lines.append("\n[MATCHED DOMAINS]")
    if r["matched_domains"]:
        for d in r["matched_domains"]:
            lines.append(
                f"  {d['name']:<30} score={d['score']}  "
                f"keywords={d['matched_keywords']}  actors={d['typical_actors']}"
            )
    else:
        lines.append("  (none — falling back to generic component chain)")

    if r.get("matched_subtypes"):
        lines.append("\n[MATCHED SUBTYPES]")
        for st in r["matched_subtypes"]:
            lines.append(
                f"  {st['name']:<30} parent={st['parent_domain']}  "
                f"score={st['score']}  keywords={st['matched_keywords']}"
            )

    lines.append(f"\n[ACTORS]  {r['actors']}")

    lines.append("\n[COMPONENTS]")
    for comp in r["components"]:
        lines.append(f"\n  ▸ {comp.upper()}")
        reason = r["component_reasons"][comp]
        for chunk in [reason[i:i+68] for i in range(0, len(reason), 68)]:
            lines.append(f"    {chunk}")

    if r.get("domain_patterns"):
        lines.append(f"\n[DOMAIN PATTERNS]  ({len(r['domain_patterns'])} applicable)")
        for p in r["domain_patterns"]:
            lines.append(f"\n  [{p['source']}] {p['id']}")
            desc = " ".join(p["description"].strip().split())
            for chunk in [desc[i:i+68] for i in range(0, len(desc), 68)]:
                lines.append(f"    {chunk}")

    lines.append(f"\n[RULES]  ({len(r['rules'])} applicable)")
    for rule in r["rules"]:
        lines.append(f"  [{rule['severity'].upper():<8}] {rule['id']}")
        lines.append(f"             {rule['description'][:70]}")
        if rule.get("guidance"):
            lines.append("             [GUIDANCE]")
            for gl in rule["guidance"].strip().split("\n"):
                lines.append(f"               {gl}")

    lines.append(f"\n[FILES / DIRECTORIES]  ({len(r['files'])} entries)")
    if r["files"]:
        for f in r["files"]:
            lines.append(f"\n  {f['path']}")
            lines.append(f"  type   : {f['type']}")
            if f.get("naming_hint"):
                lines.append(f"  hint   : {f['naming_hint']}")
            lines.append(f"  reason : {f['reason'][:80]}")
    else:
        lines.append("  (no domain-specific files; use naming conventions to find files)")

    lines.append("\n[EXCLUDED FROM RESOLVED CONTEXT]")
    for ex in r.get("excluded", []):
        lines.append(f"  ✕ {ex}")

    lines.append("\n" + sep)
    return "\n".join(lines)
