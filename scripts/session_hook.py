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

# ── Path setup ────────────────────────────────────────────────────────────────
plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if not plugin_root:
    print(
        "[open-context] CLAUDE_PLUGIN_ROOT not set — session hook skipped",
        file=sys.stderr,
    )
    sys.exit(0)

# ── Read stdin ────────────────────────────────────────────────────────────────
try:
    data = json.loads(sys.stdin.read())
except json.JSONDecodeError as exc:
    print(f"[open-context] Failed to parse hook JSON from stdin: {exc}", file=sys.stderr)
    sys.exit(0)

cwd = Path(data.get("cwd", ".")).resolve()

# ── Check for existing settings ───────────────────────────────────────────────
# 1. Project-scoped settings in this repo
project_settings = cwd / ".claude" / "oc-settings.yaml"

# 2. Global settings in CLAUDE_PLUGIN_DATA
plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA", "")
global_settings = Path(plugin_data) / "open-context" / "settings.json" if plugin_data else None

settings_found = project_settings.exists() or (
    global_settings is not None and global_settings.exists()
)

if settings_found:
    sys.exit(0)  # configured — silent no-op

# 3. Also skip if context.yaml already exists (project was set up manually)
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
    sys.exit(0)  # has context.yaml — skip wizard

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

output = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": trigger,
    }
}
print(json.dumps(output))
sys.exit(0)
