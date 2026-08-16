#!/usr/bin/env python3
"""
UserPromptSubmit hook — resolves the incoming prompt against the project's
context.yaml and injects matched context as additionalContext.

All errors go to stderr. stdout is either a valid JSON response or empty.
An empty stdout + exit 0 is a deliberate silent no-op (Q1, Q8).
"""
import json
import os
import sys
from pathlib import Path

# ── Path setup (Q5) ──────────────────────────────────────────────────────────
plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if not plugin_root:
    print(
        "[open-context] CLAUDE_PLUGIN_ROOT not set — hook not running inside Claude Code plugin",
        file=sys.stderr,
    )
    sys.exit(0)

sys.path.insert(0, str(Path(plugin_root) / "src"))
sys.path.insert(0, str(Path(plugin_root) / "vendor"))

from open_context import load_context, resolve, format_report  # noqa: E402

# ── Constants ────────────────────────────────────────────────────────────────
MAX_CHARS = 9500

# ── Read stdin ───────────────────────────────────────────────────────────────
try:
    data = json.loads(sys.stdin.read())
except json.JSONDecodeError as exc:
    print(f"[open-context] Failed to parse hook JSON from stdin: {exc}", file=sys.stderr)
    sys.exit(0)

prompt = data.get("prompt") or data.get("user_prompt", "")
cwd = Path(data.get("cwd", "."))

# ── Locate context.yaml (Q2) ─────────────────────────────────────────────────
context_path: str | None = None

env_path = os.environ.get("OPEN_CONTEXT_FILE")
if env_path:
    if Path(env_path).exists():
        context_path = env_path
    else:
        print(
            f"[open-context] OPEN_CONTEXT_FILE set but not found: {env_path}",
            file=sys.stderr,
        )
        # fall through to convention-based search

if not context_path:
    candidates: list[Path] = [
        cwd / ".claude" / "context.yaml",
        cwd / "context.yaml",
    ]
    # traverse up to git root
    d = cwd.resolve()
    while d != d.parent:
        if (d / ".git").exists():
            candidates.append(d / "context.yaml")
            break
        d = d.parent

    for c in candidates:
        if c.exists():
            context_path = str(c)
            break

if not context_path:
    sys.exit(0)  # no context.yaml anywhere — silent no-op

# ── Resolve (Q1) ─────────────────────────────────────────────────────────────
try:
    context = load_context(context_path)
    result = resolve(prompt, context)
except Exception as exc:
    print(f"[open-context] Resolver error: {exc}", file=sys.stderr)
    sys.exit(0)

# Check matched_domains BEFORE calling format_report (Q1 — critical)
if not result.get("matched_domains"):
    sys.exit(0)  # silent no-op — stdout must be empty

# ── Format + truncate at section boundary (Q4) ───────────────────────────────
report = format_report(result)

if len(report) > MAX_CHARS:
    truncated = report[:MAX_CHARS]
    # All section headers start with "\n[" — find last clean section boundary
    last_boundary = truncated.rfind("\n[")
    if last_boundary > 0:
        report = truncated[:last_boundary]
    else:
        # No section boundary found — fall back to last complete line
        last_newline = truncated.rfind("\n")
        report = truncated[:last_newline] if last_newline > 0 else truncated
    report += '\n[Context truncated — run /oc-resolve for full output]'

# ── Emit JSON (Q8) ───────────────────────────────────────────────────────────
# additionalContext must be nested inside hookSpecificOutput, not top-level.
output = {
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": report,
    }
}
print(json.dumps(output))
sys.exit(0)
