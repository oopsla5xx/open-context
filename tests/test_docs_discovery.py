"""
Unit tests for docs_discovery.py (Việc 1 — deterministic doc listing).

Direct-import unit tests, not subprocess integration tests like
test_hook_integration.py — docs_discovery.py is a plain deterministic
module with no hook/CLI-boundary concerns to exercise as a subprocess.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PLUGIN_ROOT / "src"))
sys.path.insert(0, str(PLUGIN_ROOT / "vendor"))

from open_context.docs_discovery import discover_docs  # noqa: E402


def test_empty_repo_returns_no_docs(tmp_path):
    result = discover_docs(tmp_path)
    assert result["docs_found"] == []
    assert result["repo"] == str(tmp_path.resolve())


def test_finds_fixed_names_at_root(tmp_path):
    (tmp_path / "README.md").write_text("readme")
    (tmp_path / "CLAUDE.md").write_text("claude")
    (tmp_path / "AGENTS.md").write_text("agents")

    result = discover_docs(tmp_path)
    found = {d["path"]: d["kind"] for d in result["docs_found"]}
    assert found == {
        "README.md": "README.md",
        "CLAUDE.md": "CLAUDE.md",
        "AGENTS.md": "AGENTS.md",
    }


def test_finds_fixed_names_at_nested_depth(tmp_path):
    nested = tmp_path / "app" / "policies"
    nested.mkdir(parents=True)
    (nested / "AGENTS.md").write_text("policy agent rules")

    result = discover_docs(tmp_path)
    paths = [d["path"] for d in result["docs_found"]]
    assert "app/policies/AGENTS.md" in paths


def test_case_insensitive_fixed_name_match(tmp_path):
    (tmp_path / "readme.md").write_text("lower")
    nested = tmp_path / "sub"
    nested.mkdir()
    (nested / "Claude.MD").write_text("mixed case")

    result = discover_docs(tmp_path)
    found = {d["path"]: d["kind"] for d in result["docs_found"]}
    assert found["readme.md"] == "README.md"
    assert found["sub/Claude.MD"] == "CLAUDE.md"


def test_finds_nested_docs_dir_markdown(tmp_path):
    rules_dir = tmp_path / "docs" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "security-checklist.md").write_text("security rules")
    (tmp_path / "docs" / "overview.md").write_text("overview")

    result = discover_docs(tmp_path)
    found = {d["path"]: d["kind"] for d in result["docs_found"]}
    assert found["docs/rules/security-checklist.md"] == "docs_md"
    assert found["docs/overview.md"] == "docs_md"


def test_non_docs_directory_markdown_not_matched(tmp_path):
    other = tmp_path / "notes"
    other.mkdir()
    (other / "random.md") .write_text("not under docs/, not a fixed name")

    result = discover_docs(tmp_path)
    assert result["docs_found"] == []


def test_ignored_directories_never_descended_into(tmp_path):
    for ignored in ("node_modules", "vendor", ".git", "dist", "build", ".open-context"):
        d = tmp_path / ignored
        d.mkdir()
        (d / "README.md").write_text("should never be found")
        docs_sub = d / "docs"
        docs_sub.mkdir()
        (docs_sub / "x.md").write_text("should never be found either")

    (tmp_path / "README.md").write_text("real readme")

    result = discover_docs(tmp_path)
    paths = [d["path"] for d in result["docs_found"]]
    assert paths == ["README.md"]


def test_context_decisions_md_not_matched(tmp_path):
    # Not one of the 3 fixed names, and not under a docs/ directory —
    # confirms the intended boundary (this file type is handled separately,
    # not by Việc 1's glob).
    (tmp_path / "context-decisions.md").write_text("rationale")

    result = discover_docs(tmp_path)
    assert result["docs_found"] == []
