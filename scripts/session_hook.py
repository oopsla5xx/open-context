#!/usr/bin/env python3
"""
SessionStart hook — detects first-run (no open-context settings found) and
injects a wizard trigger into additionalContext so Claude starts /oc-setup
automatically without the user needing to invoke any command.

All errors go to stderr. stdout is either a valid JSON response or empty.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hook_utils import check_plugin_root, read_stdin_json  # noqa: E402

check_plugin_root("session hook")

data = read_stdin_json()
cwd = Path(data.get("cwd", ".")).resolve()

# ── Check for existing settings ───────────────────────────────────────────────
project_settings = cwd / ".claude" / "oc-settings.yaml"

plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA", "")
global_settings = (
    Path(plugin_data) / "open-context" / "settings.json" if plugin_data else None
)

settings_found = project_settings.exists() or (
    global_settings is not None and global_settings.exists()
)

if settings_found:
    sys.exit(0)

# Also skip if context.yaml already exists (project was set up manually)
context_candidates = [
    cwd / ".claude" / "context.yaml",
    cwd / "context.yaml",
]
d = cwd
while d != d.parent:
    if (d / ".git").exists():
        context_candidates.append(d / "context.yaml")
        break
    d = d.parent

if any(c.exists() for c in context_candidates):
    sys.exit(0)

# ── Inject wizard trigger ─────────────────────────────────────────────────────
trigger = (
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

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": trigger,
    }
}))
sys.exit(0)
