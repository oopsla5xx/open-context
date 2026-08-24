---
name: oc-validate
description: Run phrasing coverage tests and amplification safety checks against the project's context.yaml. Reports per-domain pass/fail rates, risk levels, and amplification warnings.
---

Run Open:Context phrasing coverage + amplification safety validation.

## Steps

1. Locate `context.yaml` by checking in order:
   - `.open-context/context.yaml` in the current working directory
   - `context.yaml` in the current working directory
   - `context.yaml` at the git repository root (traverse up until `.git` is found)
   If `OPEN_CONTEXT_FILE` is set in the environment, use that path instead.

2. Look for a `tests/` directory next to the located `context.yaml` file.

3. Run:
   ```
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/src:${CLAUDE_PLUGIN_ROOT}/vendor" \
     python3 -m open_context.cli validate \
     --context <path-to-context.yaml> \
     --tests <path-to-tests-dir>
   ```
   Omit `--tests` if no tests directory is found; the CLI will report which domains lack test coverage.

4. Show the full output: per-domain pass/fail rates, risk levels, and any amplification warnings.

If no `context.yaml` is found, say so clearly and suggest running `/oc-setup` to generate one.
