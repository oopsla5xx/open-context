#!/bin/bash
# Entrypoint for the UserPromptSubmit hook.
# Tries Python candidates in order, combining version-check and invocation
# into a single subprocess call (Q7 — no extra spawn for check).
# All error output goes to stderr; stdout is left for the Python script.

HOOK_SCRIPT="${CLAUDE_PLUGIN_ROOT}/scripts/resolve_hook.py"

for PY in python3 python3.12 python3.11 python3.10 python3.9 "py -3" python; do
    if $PY -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)" 2>/dev/null; then
        exec $PY "$HOOK_SCRIPT"
    fi
done

echo "[open-context] No compatible Python (>=3.9) found on PATH — context not injected" >&2
exit 0
