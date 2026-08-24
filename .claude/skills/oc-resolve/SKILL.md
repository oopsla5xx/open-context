---
name: oc-resolve
description: Manually resolve a task against the project's context.yaml — shows which domains, components, files, and rules would be injected by the hook. Use for debugging routing and keyword coverage.
---

Run the Open:Context resolver for this task and display the full output.

**Task:** $ARGUMENTS

## Steps

1. Locate `context.yaml` by checking in order:
   - `.open-context/context.yaml` in the current working directory
   - `context.yaml` in the current working directory
   - `context.yaml` at the git repository root (traverse up until `.git` is found)
   If `OPEN_CONTEXT_FILE` is set in the environment, use that path instead.

2. Run:
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/src/open_context/cli.py" resolve <task-words> \
     --context <path-to-context.yaml>
   ```
   Pass the task as individual words after `resolve` (not a single quoted string).

3. Show the complete output: matched domains, scores, component chain, applicable rules, and resolved files. Include domains that scored below threshold so the user can diagnose why a task didn't match.

If no `context.yaml` is found, say so clearly and suggest running `/oc-setup` to generate one.
