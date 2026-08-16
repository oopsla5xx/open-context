#!/bin/bash
# SessionStart hook entrypoint — finds a compatible Python (>=3.9) and runs session_hook.py.
# Errors go to stderr only; stdout must be empty or valid JSON.
HOOK_SCRIPT="${CLAUDE_PLUGIN_ROOT}/scripts/session_hook.py"

for PY in python3 python3.12 python3.11 python3.10 python3.9 "py -3" python; do
    if $PY -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)" 2>/dev/null; then
        exec $PY "$HOOK_SCRIPT"
    fi
done

echo "[open-context] No compatible Python (>=3.9) found on PATH — session hook skipped" >&2
exit 0
