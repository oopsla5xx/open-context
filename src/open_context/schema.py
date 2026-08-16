"""
Open:Context — context.yaml schema validator.

Checks that a loaded context dict has the required structure before
passing it to the resolver. Returns a list of error strings (empty = valid).
"""


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

    # L2 — architecture
    arch = ctx.get("architecture")
    if not arch:
        errors.append("missing required key: 'architecture'")
    elif not isinstance(arch.get("flow"), list) or not arch["flow"]:
        errors.append("architecture.flow must be a non-empty list of component names")

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

    return errors
