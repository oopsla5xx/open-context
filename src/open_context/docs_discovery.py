"""
Open:Context — project doc discovery ("Việc 1").

A pure, deterministic file listing — no LLM, no scoring, no confidence.
Whether a file named AGENTS.md exists at a given path isn't uncertain the
way a detected framework version can be; there's nothing to blend into a
score. This is the code half of the docs-first split (see tasks/plan.md):
this module only finds candidate doc files, it never reads their content
or decides what belongs in context.yaml — that's the agentic /oc-setup
step's job (Việc 2).

Matches, at any directory depth:
  - README.md, CLAUDE.md, AGENTS.md (case-insensitive exact filename)
  - every *.md file under any directory named "docs"

Ignored directories are never descended into (not filtered after the
fact) — this matters for large monorepos where node_modules alone can
contain thousands of README.md files.
"""
from __future__ import annotations

from pathlib import Path

IGNORED_DIR_NAMES = {"node_modules", "vendor", ".git", "dist", "build", ".open-context"}

_FIXED_NAME_KINDS = {
    "readme.md": "README.md",
    "claude.md": "CLAUDE.md",
    "agents.md": "AGENTS.md",
}


def _walk(dir_path: Path, under_docs: bool, found: list) -> None:
    try:
        entries = sorted(dir_path.iterdir(), key=lambda p: p.name)
    except OSError:
        return

    for entry in entries:
        if entry.is_dir():
            if entry.name in IGNORED_DIR_NAMES:
                continue
            _walk(entry, under_docs or entry.name == "docs", found)
        elif entry.is_file():
            lower_name = entry.name.lower()
            kind = _FIXED_NAME_KINDS.get(lower_name)
            if kind is not None:
                found.append((entry, kind))
            elif under_docs and lower_name.endswith(".md"):
                found.append((entry, "docs_md"))


def discover_docs(repo: "Path | str") -> dict:
    """
    Recursively list README.md/CLAUDE.md/AGENTS.md and docs/**/*.md under
    repo, skipping IGNORED_DIR_NAMES entirely.

    Returns:
      {
        "repo": str,
        "docs_found": [ {"path": "<repo-relative, forward-slash>", "kind": "README.md"|"CLAUDE.md"|"AGENTS.md"|"docs_md"} ]
      }
    """
    root = Path(repo).resolve()
    found: list = []
    _walk(root, under_docs=False, found=found)
    found.sort(key=lambda pair: str(pair[0]))

    return {
        "repo": str(root),
        "docs_found": [
            {"path": path.relative_to(root).as_posix(), "kind": kind}
            for path, kind in found
        ],
    }
