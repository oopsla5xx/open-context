#!/usr/bin/env python3
"""
SessionStart hook — detects first-run (no open-context settings found) and
injects a wizard trigger into additionalContext so Claude starts /oc-setup
automatically without the user needing to invoke any command.

All errors go to stderr. stdout is either a valid JSON response or empty.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hook_utils import check_plugin_root, read_stdin_json, is_first_run, WIZARD_TRIGGER  # noqa: E402

check_plugin_root("session hook")

data = read_stdin_json()
cwd = Path(data.get("cwd", "."))

if not is_first_run(cwd):
    sys.exit(0)

# ── Inject wizard trigger ─────────────────────────────────────────────────────
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": WIZARD_TRIGGER,
    }
}))
sys.exit(0)
