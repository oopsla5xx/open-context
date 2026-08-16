"""Shared utilities for open-context hook scripts."""
import json
import os
import sys
from pathlib import Path


def check_plugin_root(hook_label: str) -> str:
    """Return CLAUDE_PLUGIN_ROOT or exit 0 with a stderr message."""
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root:
        print(
            f"[open-context] CLAUDE_PLUGIN_ROOT not set — {hook_label} skipped",
            file=sys.stderr,
        )
        sys.exit(0)
    return plugin_root


def read_stdin_json() -> dict:
    """Read and parse JSON from stdin, exit 0 on parse error."""
    try:
        return json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        print(
            f"[open-context] Failed to parse hook JSON from stdin: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)


def setup_plugin_path(plugin_root: str) -> None:
    """Insert src/ and vendor/ from the plugin root into sys.path."""
    root = Path(plugin_root)
    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root / "vendor"))


WIZARD_TRIGGER = (
    "[open-context] First-run setup detected — no configuration found for this project.\n\n"
    "Start the open-context setup wizard now. Do not wait for the user to invoke a command — "
    "begin the `/oc-setup` skill immediately by asking the first setup question:\n\n"
    "**Question 1 — Scope**\n"
    "Where should open-context save its settings?\n"
    "1. `project` — saved to `.claude/oc-settings.yaml` in this repo (shared with the team)\n"
    "2. `global` — saved to your machine only (applies to all your projects)\n\n"
    "After the user answers, continue with Questions 2–5 per the `/oc-setup` skill, "
    "then generate context.yaml, test files, and run validation automatically."
)


def context_yaml_candidates(cwd: "Path") -> "list[Path]":
    """Return candidate context.yaml paths for cwd (local + git-root)."""
    cwd = Path(cwd).resolve()
    candidates = [cwd / ".claude" / "context.yaml", cwd / "context.yaml"]
    d = cwd
    while d != d.parent:
        if (d / ".git").exists():
            candidates.append(d / "context.yaml")
            break
        d = d.parent
    return candidates


def is_first_run(cwd: "Path") -> bool:
    """Return True if no open-context config exists for this project."""
    cwd = Path(cwd).resolve()

    if (cwd / ".claude" / "oc-settings.yaml").exists():
        return False

    plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA", "")
    if plugin_data and (Path(plugin_data) / "open-context" / "settings.json").exists():
        return False

    return not any(c.exists() for c in context_yaml_candidates(cwd))
