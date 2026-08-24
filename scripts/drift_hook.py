#!/usr/bin/env python3
"""
PreToolUse hook (matcher: Edit|Write) — domain-drift detection.

The UserPromptSubmit hook (resolve_hook.py) only sees the task text at the
start of a turn and injects context for the domain(s) that match it. If
Claude then edits a file belonging to a *different* domain later in the
same turn — one whose rules/patterns were never surfaced — this hook
catches that and injects just that domain's rules/patterns before the
write happens.

State: which domains have already been surfaced this turn lives in a
per-session_id file (see hook_utils.session_state_path), written by
resolve_hook.py at UserPromptSubmit (reset) and updated here (merge) as
new domains get surfaced. This hook never blocks the tool call — it only
ever adds additionalContext or exits silently.

All errors go to stderr. stdout is either a valid JSON response or empty.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hook_utils import (
    add_session_domains, check_plugin_root, context_yaml_candidates,
    drift_detection_enabled, read_session_domains, repo_root_for_context,
    read_stdin_json, setup_plugin_path,
)

plugin_root = check_plugin_root("PreToolUse drift hook")
setup_plugin_path(plugin_root)

from open_context import load_context, domains_by_path, format_drift_report
from open_context.resolver import select_rules

data = read_stdin_json()

if data.get("tool_name") not in ("Edit", "Write"):
    sys.exit(0)

file_path = (data.get("tool_input") or {}).get("file_path")
if not file_path:
    sys.exit(0)

cwd = Path(data.get("cwd", "."))
session_id = data.get("session_id", "")

if not drift_detection_enabled(cwd):
    sys.exit(0)

context_path = None
for c in context_yaml_candidates(cwd):
    if c.exists():
        context_path = c
        break
if not context_path:
    sys.exit(0)

try:
    context = load_context(context_path)
except Exception as exc:  # pylint: disable=broad-except
    print(f"[open-context] drift hook: failed to load context.yaml: {exc}", file=sys.stderr)
    sys.exit(0)

repo_root = repo_root_for_context(context_path)
try:
    rel_path = Path(file_path).resolve().relative_to(repo_root)
except ValueError:
    sys.exit(0)  # file is outside the repo root — no domain can own it

try:
    matched = domains_by_path(context, str(rel_path))
except Exception as exc:  # pylint: disable=broad-except
    print(f"[open-context] drift hook: resolve error: {exc}", file=sys.stderr)
    sys.exit(0)

if not matched:
    sys.exit(0)

already_surfaced = read_session_domains(session_id)
new_domains = [d for d in matched if d["name"] not in already_surfaced]
if not new_domains:
    sys.exit(0)

domain_names = {d["name"] for d in new_domains}
rules = select_rules(context, domain_names)
report = format_drift_report(str(rel_path), new_domains, rules)

add_session_domains(session_id, [d["name"] for d in new_domains])

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": report,
    }
}))
sys.exit(0)
