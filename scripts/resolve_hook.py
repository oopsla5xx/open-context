#!/usr/bin/env python3
"""
UserPromptSubmit hook — resolves the incoming prompt against the project's
context.yaml and injects matched context as additionalContext.

All errors go to stderr. stdout is either a valid JSON response or empty.
An empty stdout + exit 0 is the deliberate silent no-op.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hook_utils import (  # noqa: E402
    check_plugin_root, read_stdin_json, setup_plugin_path,
    context_yaml_candidates, is_first_run, WIZARD_TRIGGER,
)

plugin_root = check_plugin_root("UserPromptSubmit hook")
setup_plugin_path(plugin_root)

from open_context import load_context, resolve, format_report  # noqa: E402

MAX_CHARS = 9500

data = read_stdin_json()
prompt = data.get("prompt") or data.get("user_prompt", "")
cwd = Path(data.get("cwd", "."))

# ── Locate context.yaml ───────────────────────────────────────────────────────
context_path = None

env_path = os.environ.get("OPEN_CONTEXT_FILE")
if env_path:
    if Path(env_path).exists():
        context_path = env_path
    else:
        print(
            f"[open-context] OPEN_CONTEXT_FILE set but not found: {env_path}",
            file=sys.stderr,
        )

if not context_path:
    for c in context_yaml_candidates(cwd):
        if c.exists():
            context_path = str(c)
            break

if not context_path:
    if is_first_run(cwd):
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": WIZARD_TRIGGER,
            }
        }))
    sys.exit(0)

# ── Resolve ───────────────────────────────────────────────────────────────────
try:
    context = load_context(context_path)
    result = resolve(prompt, context)
except Exception as exc:  # pylint: disable=broad-except
    print(f"[open-context] Resolver error: {exc}", file=sys.stderr)
    sys.exit(0)

if not result.get("matched_domains"):
    sys.exit(0)

# ── Format + truncate at section boundary ─────────────────────────────────────
report = format_report(result)

if len(report) > MAX_CHARS:
    truncated = report[:MAX_CHARS]
    last_boundary = truncated.rfind("\n[")
    if last_boundary > 0:
        report = truncated[:last_boundary]
    else:
        last_newline = truncated.rfind("\n")
        report = truncated[:last_newline] if last_newline > 0 else truncated
    report += "\n[Context truncated — run /oc-resolve for full output]"

# ── Token savings stats ───────────────────────────────────────────────────────
def _kb(n: int) -> str:
    return f"{n / 1024:.1f} KB"

try:
    full_result = resolve(prompt, context, include_all_domains=True)
    full_chars = len(format_report(full_result))
    injected_chars = len(report)
    # full_chars is >= the pre-truncation report (full_result is a domain
    # superset), but injected_chars includes the truncation notice suffix,
    # so it can marginally exceed full_chars. max(0, ...) guards the display.
    if full_chars > 0:
        savings_pct = max(0, int((full_chars - injected_chars) / full_chars * 100))
        report += (
            f"\n[open-context] {savings_pct}% token reduction"
            f" ({_kb(injected_chars)} injected vs {_kb(full_chars)} full context)"
        )
except Exception as exc:  # pylint: disable=broad-except
    print(f"[open-context] stats error (non-fatal): {type(exc).__name__}: {exc}", file=sys.stderr)

# ── Emit JSON ─────────────────────────────────────────────────────────────────
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": report,
    }
}))
sys.exit(0)
