"""
Open:Context — Phase 4a stack discovery.

Deterministic detectors for language/framework/version/package-manager/
database/ORM/test-framework, one per ecosystem (Ruby, Node, Python). No LLM
calls — same "zero-LLM core" principle as resolver.py/validator.py.

Each detected field is returned as {"value", "confidence", "source"} rather
than a single blended score: a field read from a structured manifest
(Gemfile, package.json, pyproject.toml) is near-certain; a field only
recoverable from prose docs (CLAUDE.md/AGENTS.md/README.md) is markedly
less certain, and callers should treat it accordingly.

Non-recursive by design: detect() only reads files directly under the given
repo path, mirroring `architecture validate --repo --path` — a monorepo
with multiple ecosystems in different subdirectories (e.g. a Python
backend/ next to a Next.js frontend-nextjs/) is handled by calling detect()
once per subdirectory, not by one call auto-discovering every ecosystem.

Known limitation (not handled — no heuristic exists yet to detect this
reliably): a root-level package.json in a monorepo can be a thin wrapper
that only proxies scripts into a real app subdirectory, yet still lists
that app's framework as a direct dependency (e.g. to keep `npm run dev`
working at the root). detect() has no way to distinguish that from a real
app manifest, so it may report a framework that isn't actually rooted at
the scanned path — resolve against the actual app subdirectory instead of
trusting a monorepo root scan at face value.

Confidence scale: 0.0-1.0 float. Thresholds/bands are a starting point to
be tuned after seeing real detect() output on ground-truth repos, not a
final calibration.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PROSE_DOC_NAMES = ("CLAUDE.md", "AGENTS.md", "README.md")


def _field(value, confidence: float, source: str) -> dict:
    return {"value": value, "confidence": round(confidence, 2), "source": source}


def _read_prose_docs(repo: Path) -> str:
    chunks = []
    for name in PROSE_DOC_NAMES:
        p = repo / name
        if p.is_file():
            chunks.append(p.read_text(errors="ignore"))
    return "\n".join(chunks)


def _augment_version_from_prose(repo: Path, fields: dict, value_key: str, version_key: str) -> None:
    """If `value_key` was found from a structured file but has no version, try to
    recover a version number for it from prose docs — lower confidence, clearly
    sourced as prose so callers don't treat it as equal to a structured-file read."""
    field = fields.get(value_key)
    if not field or not field.get("value") or version_key in fields:
        return
    prose = _read_prose_docs(repo)
    if not prose:
        return
    m = re.search(re.escape(str(field["value"])) + r"\s+([\d]+(?:\.[\d]+){0,2})", prose, re.I)
    if m:
        fields[version_key] = _field(
            m.group(1), 0.6, f"prose doc ({'/'.join(PROSE_DOC_NAMES)}) — not a structured config source"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Ruby / Rails
# ─────────────────────────────────────────────────────────────────────────────

_DB_ADAPTER_NAMES = {
    "postgresql": "PostgreSQL",
    "mysql2": "MySQL",
    "sqlite3": "SQLite",
}


def detect_ruby(repo: Path) -> dict | None:
    gemfile = repo / "Gemfile"
    if not gemfile.is_file():
        return None

    text = gemfile.read_text(errors="ignore")
    fields: dict = {"language": _field("Ruby", 0.99, "Gemfile present")}

    m = re.search(r"^\s*ruby\s+['\"]([\d.]+)['\"]", text, re.M)
    if m:
        fields["language_version"] = _field(m.group(1), 0.97, "Gemfile `ruby` directive")
    else:
        rv_file = repo / ".ruby-version"
        if rv_file.is_file():
            v = rv_file.read_text(errors="ignore").strip()
            v = re.sub(r"^ruby-", "", v)
            fields["language_version"] = _field(v, 0.9, ".ruby-version")

    m = re.search(r"gem\s+['\"]rails['\"]\s*,\s*['\"]([^'\"]+)['\"]", text)
    if m:
        fields["framework"] = _field("Rails", 0.98, "Gemfile `gem 'rails'` version pin")
        fields["framework_version"] = _field(m.group(1), 0.98, "Gemfile `gem 'rails'` version pin")
    elif re.search(r"gem\s+['\"]rails['\"]", text):
        fields["framework"] = _field("Rails", 0.9, "Gemfile `gem 'rails'` (no version pin)")

    fields["package_manager"] = _field(
        "Bundler", 0.95 if (repo / "Gemfile.lock").is_file() else 0.7,
        "Gemfile.lock present" if (repo / "Gemfile.lock").is_file() else "Gemfile present (no Gemfile.lock)"
    )

    db_yml = repo / "config" / "database.yml"
    if db_yml.is_file():
        db_text = db_yml.read_text(errors="ignore")
        m = re.search(r"adapter:\s*(\w+)", db_text)
        if m:
            adapter = m.group(1)
            fields["database"] = _field(
                _DB_ADAPTER_NAMES.get(adapter, adapter), 0.85,
                "config/database.yml adapter (server version not present in structured config)"
            )
            if fields.get("framework", {}).get("value") == "Rails":
                fields["orm"] = _field("ActiveRecord", 0.85, "Rails default (config/database.yml present)")

    # A Rails app's primary relational DB (above) does not preclude an additional
    # datastore wired in through its own gem/ORM — e.g. Mongoid for MongoDB used
    # alongside ActiveRecord. Detected independently; not mutually exclusive with
    # the block above (real repos have shown both present at once).
    if re.search(r"gem\s+['\"]mongoid['\"]", text):
        has_mongoid_config = (repo / "config" / "mongoid.yml").is_file()
        fields["database_secondary"] = _field(
            "MongoDB", 0.9 if has_mongoid_config else 0.75,
            "Gemfile `gem 'mongoid'`" + (" + config/mongoid.yml present" if has_mongoid_config else "")
        )
        fields["orm_secondary"] = _field("Mongoid", 0.9, "Gemfile `gem 'mongoid'`")
    elif re.search(r"gem\s+['\"]sequel['\"]", text):
        fields["orm_secondary"] = _field(
            "Sequel", 0.7, "Gemfile `gem 'sequel'` (target database unknown from Gemfile alone)"
        )

    has_rspec_dir = (repo / "spec").is_dir()
    has_rspec_file = (repo / ".rspec").is_file()
    has_rspec_gem = bool(re.search(r"gem\s+['\"]rspec", text))
    if has_rspec_dir or has_rspec_file or has_rspec_gem:
        conf = 0.5
        sources = []
        if has_rspec_gem:
            conf += 0.3
            sources.append("Gemfile rspec gem")
        if has_rspec_dir:
            conf += 0.1
            sources.append("spec/ directory")
        if has_rspec_file:
            conf += 0.1
            sources.append(".rspec file")
        fields["test_framework"] = _field("RSpec", min(conf, 0.97), " + ".join(sources))
    elif (repo / "test").is_dir():
        fields["test_framework"] = _field("Minitest", 0.6, "test/ directory (Rails default, no RSpec signal)")

    _augment_version_from_prose(repo, fields, "database", "database_version")
    return {"ecosystem": "ruby", "fields": fields}


# ─────────────────────────────────────────────────────────────────────────────
# Node / Next.js
# ─────────────────────────────────────────────────────────────────────────────

_NODE_FRAMEWORKS = (
    ("next", "Next.js", 0.97),
    ("nuxt", "Nuxt", 0.95),
    ("@nestjs/core", "NestJS", 0.95),
    ("express", "Express", 0.9),
)
_NODE_ORMS = (
    ("@prisma/client", "Prisma", 0.9),
    ("prisma", "Prisma", 0.9),
    ("drizzle-orm", "Drizzle", 0.9),
    ("mongoose", "Mongoose", 0.9),
    ("sequelize", "Sequelize", 0.9),
)
_NODE_TEST_FRAMEWORKS = (
    ("vitest", "Vitest", 0.9),
    ("jest", "Jest", 0.9),
    ("@playwright/test", "Playwright", 0.85),
)


def detect_node(repo: Path) -> dict | None:
    pkg_path = repo / "package.json"
    if not pkg_path.is_file():
        return None

    try:
        data = json.loads(pkg_path.read_text(errors="ignore"))
    except json.JSONDecodeError:
        return {"ecosystem": "node", "fields": {}, "error": "package.json present but not valid JSON"}

    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    fields: dict = {"language": _field("JavaScript", 0.9, "package.json present")}

    if "typescript" in deps or (repo / "tsconfig.json").is_file():
        fields["language"] = _field("TypeScript", 0.9, "typescript dependency or tsconfig.json present")
        ts_range = deps.get("typescript")
        if ts_range:
            fields["language_version"] = _field(
                re.sub(r"^[\^~]", "", ts_range), 0.6,
                "package.json typescript dependency range (not a resolved exact version)"
            )

    engines_node = data.get("engines", {}).get("node")
    if engines_node:
        fields["runtime_version"] = _field(engines_node, 0.8, "package.json engines.node")

    for dep_name, framework_name, conf in _NODE_FRAMEWORKS:
        if dep_name in deps:
            fields["framework"] = _field(framework_name, conf, f"package.json dependency `{dep_name}`")
            fields["framework_version"] = _field(
                re.sub(r"^[\^~]", "", deps[dep_name]), min(conf, 0.9),
                f"package.json `{dep_name}` version range (not a resolved exact version)"
            )
            break

    if (repo / "pnpm-lock.yaml").is_file():
        fields["package_manager"] = _field("pnpm", 0.95, "pnpm-lock.yaml present")
    elif (repo / "yarn.lock").is_file():
        fields["package_manager"] = _field("Yarn", 0.95, "yarn.lock present")
    elif (repo / "package-lock.json").is_file():
        fields["package_manager"] = _field("npm", 0.95, "package-lock.json present")
    else:
        fields["package_manager"] = _field("npm", 0.5, "no lockfile found; npm assumed as default")

    for dep_name, orm_name, conf in _NODE_ORMS:
        if dep_name in deps:
            fields["orm"] = _field(orm_name, conf, f"package.json dependency `{dep_name}`")
            break

    for dep_name, tf_name, conf in _NODE_TEST_FRAMEWORKS:
        if dep_name in deps:
            fields["test_framework"] = _field(tf_name, conf, f"package.json dependency `{dep_name}`")
            break

    return {"ecosystem": "node", "fields": fields}


# ─────────────────────────────────────────────────────────────────────────────
# Python
# ─────────────────────────────────────────────────────────────────────────────

_PY_FRAMEWORKS = (
    ("fastapi", "FastAPI", 0.95),
    ("django", "Django", 0.95),
    ("flask", "Flask", 0.9),
)


def _parse_pyproject(text: str) -> tuple[str | None, set[str]]:
    """Returns (requires_python, dependency_names). Uses tomllib (stdlib, py3.11+)
    when parseable; falls back to a crude regex scan otherwise.

    tomllib is imported here, not at module top-level: the hook scripts this
    package is also imported by (scripts/resolve_hook.py, via `open_context`
    package `__init__.py`) support Python >=3.9 (see CLAUDE.md's "Known
    Discrepancy"), while tomllib is stdlib only from 3.11 — a top-level
    import would crash the hook path entirely on 3.9/3.10, not just this
    one field. Catching broadly here is deliberate for the same reason:
    on <3.11 the failure is ImportError, on malformed TOML it's
    tomllib.TOMLDecodeError, and either way the fallback regex scan below
    is the correct, safe response.
    """
    try:
        import tomllib  # pylint: disable=import-outside-toplevel,import-error
        data = tomllib.loads(text)
    except Exception:  # pylint: disable=broad-exception-caught
        m = re.search(r'requires-python\s*=\s*"([^"]+)"', text)
        requires_python = m.group(1) if m else None
        deps = {d.lower() for d in re.findall(r'"([A-Za-z0-9_\-]+)(?:[>=<~! ].*?)?"', text)}
        return requires_python, deps

    project = data.get("project", {})
    requires_python = project.get("requires-python")
    deps = set()
    for dep in project.get("dependencies", []):
        m = re.match(r"[A-Za-z0-9_\-.]+", dep)
        if m:
            deps.add(m.group(0).lower())

    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    if not requires_python and "python" in poetry_deps:
        requires_python = str(poetry_deps["python"])
    deps |= {k.lower() for k in poetry_deps.keys() if k.lower() != "python"}

    return requires_python, deps


def _parse_requirements(text: str) -> set[str]:
    deps = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        m = re.match(r"[A-Za-z0-9_\-.]+", line)
        if m:
            deps.add(m.group(0).lower())
    return deps


def detect_python(repo: Path) -> dict | None:
    pyproject_path = repo / "pyproject.toml"
    requirements_path = repo / "requirements.txt"
    has_pyproject = pyproject_path.is_file()
    has_requirements = requirements_path.is_file()
    if not has_pyproject and not has_requirements:
        return None

    requires_python = None
    pyproject_deps: set[str] = set()
    if has_pyproject:
        requires_python, pyproject_deps = _parse_pyproject(pyproject_path.read_text(errors="ignore"))

    requirements_deps: set[str] = set()
    if has_requirements:
        requirements_deps = _parse_requirements(requirements_path.read_text(errors="ignore"))

    # pyproject.toml is the modern, richer source — prefer it on conflict, but union
    # dependency names from both for detection purposes (presence, not version).
    all_deps = pyproject_deps | requirements_deps

    fields: dict = {"language": _field("Python", 0.95, "pyproject.toml/requirements.txt present")}
    if requires_python:
        fields["language_version"] = _field(requires_python, 0.9, "pyproject.toml requires-python")

    if has_pyproject and has_requirements:
        fields["_source_conflict_note"] = (
            "both pyproject.toml and requirements.txt present — pyproject.toml is treated as the "
            "authoritative source for version/framework fields per project convention; "
            "requirements.txt is only used to widen dependency-presence detection"
        )

    for dep_name, framework_name, conf in _PY_FRAMEWORKS:
        if dep_name in all_deps:
            fields["framework"] = _field(framework_name, conf, f"dependency `{dep_name}` found")
            break

    if "sqlalchemy" in all_deps:
        fields["orm"] = _field("SQLAlchemy", 0.9, "dependency `sqlalchemy` found")
    elif fields.get("framework", {}).get("value") == "Django":
        fields["orm"] = _field("Django ORM", 0.8, "Django default ORM (no separate ORM dependency found)")

    if "pytest" in all_deps:
        fields["test_framework"] = _field("pytest", 0.9, "dependency `pytest` found")

    if (repo / "poetry.lock").is_file():
        fields["package_manager"] = _field("Poetry", 0.95, "poetry.lock present")
    elif (repo / "uv.lock").is_file():
        fields["package_manager"] = _field("uv", 0.95, "uv.lock present")
    elif has_requirements:
        fields["package_manager"] = _field("pip", 0.7, "requirements.txt present (no lockfile)")

    _augment_version_from_prose(repo, fields, "framework", "framework_version")
    return {"ecosystem": "python", "fields": fields}


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

_DETECTORS = (detect_ruby, detect_node, detect_python)


def detect(repo_path: "Path | str") -> dict:
    """Run every ecosystem detector against files directly under repo_path
    (non-recursive — see module docstring). Returns 0, 1, or more ecosystem
    results; more than one means the given path itself has manifests for
    multiple ecosystems, which is reported as-is with no aggregation logic."""
    repo = Path(repo_path).resolve()
    ecosystems = [r for r in (fn(repo) for fn in _DETECTORS) if r is not None]
    return {"repo": str(repo), "ecosystems": ecosystems}
