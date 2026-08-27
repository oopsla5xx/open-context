"""
Open:Context — context.yaml schema validator.

Checks that a loaded context dict has the required structure before
passing it to the resolver. Returns a list of error strings (empty = valid).
"""


def _check_dead_keywords(label: str, keywords: list) -> list[str]:
    """
    The resolver only splits compound keywords on '_' — a keyword containing
    a literal space (e.g. 'system setting') is never split, so it silently
    degrades to a loose prefix check against the whole phrase instead of
    matching both words. Always an authoring mistake: use 'system_setting'.
    """
    errors = []
    for kw in keywords:
        if isinstance(kw, str) and " " in kw.strip():
            errors.append(
                f"{label}: keyword '{kw}' contains a space — the resolver only splits on "
                f"'_', so this will never match as intended; use '{kw.strip().replace(' ', '_')}'"
            )
    return errors


def _check_pattern_sources(label: str, patterns: list) -> list[str]:
    """
    Every pattern must cite the file it was derived from (source:) —
    traceability for docs-first synthesis: a reader should be able to
    check `source:` against the cited file rather than trust an
    unattributed LLM summary. Same requirement as rules[].source.
    """
    errors = []
    for i, p in enumerate(patterns):
        if isinstance(p, dict) and not p.get("source"):
            errors.append(
                f"{label}.patterns[{i}] ({p.get('id', '?')}): missing 'source' — every pattern must "
                f"cite the file it was derived from (a doc path, or a code file for the no-docs fallback)"
            )
    return errors


def validate_context(ctx: dict) -> list[str]:
    """
    Validate the structure of a context.yaml dict.
    Returns a list of error strings. Empty list means valid.
    """
    errors: list[str] = []

    if not isinstance(ctx, dict):
        return ["context must be a YAML mapping (dict)"]

    # L1 — project block
    project = ctx.get("project")
    if not project:
        errors.append("missing required key: 'project'")
    elif not project.get("name"):
        errors.append("project.name is required")

    # L2 — architecture (optional: a repo with no clear layered architecture
    # can omit 'architecture' entirely, or leave 'flow' empty/absent — domains
    # still route on keywords/related_components/patterns without it)
    arch = ctx.get("architecture") or {}
    if "flow" in arch and not isinstance(arch["flow"], list):
        errors.append("architecture.flow must be a list of component names when present")

    # L3 — domains
    domains = ctx.get("domains")
    if domains is None:
        errors.append("missing required key: 'domains'")
    elif not isinstance(domains, list):
        errors.append("'domains' must be a list")
    else:
        for i, d in enumerate(domains):
            if not d.get("name"):
                errors.append(f"domains[{i}]: missing 'name'")
            if not isinstance(d.get("keywords", []), list):
                errors.append(f"domains[{i}] ({d.get('name', '?')}): 'keywords' must be a list")
            else:
                errors += _check_dead_keywords(f"domains[{i}] ({d.get('name', '?')})", d.get("keywords", []))
            errors += _check_pattern_sources(f"domains[{i}] ({d.get('name', '?')})", d.get("patterns", []))
            for j, st in enumerate(d.get("subtypes", [])):
                errors += _check_dead_keywords(
                    f"domains[{i}].subtypes[{j}] ({st.get('name', '?')})", st.get("keywords", [])
                )
                errors += _check_pattern_sources(
                    f"domains[{i}].subtypes[{j}] ({st.get('name', '?')})", st.get("patterns", [])
                )

    # L4 — rules (optional but validated if present)
    rules = ctx.get("rules", [])
    if not isinstance(rules, list):
        errors.append("'rules' must be a list")
    else:
        for i, r in enumerate(rules):
            if not r.get("id"):
                errors.append(f"rules[{i}]: missing 'id'")
            if not r.get("description"):
                errors.append(f"rules[{i}] ({r.get('id', '?')}): missing 'description'")
            if not r.get("source"):
                errors.append(
                    f"rules[{i}] ({r.get('id', '?')}): missing 'source' — every rule must cite the "
                    f"file it was derived from (a doc path, or a code file for the no-docs fallback)"
                )

    return errors
