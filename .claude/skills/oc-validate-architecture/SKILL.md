---
name: oc-validate-architecture
description: Scan 6 HMVC architecture compliance rules (R1–R6) across the Rails codebase. Exits with violations list. Use for compliance checks, not routine validation.
---

Run Open:Context HMVC architecture compliance checks against the Rails codebase.

**Arguments (optional):** $ARGUMENTS

## Steps

1. Determine the Rails repo root to scan:
   - If `$ARGUMENTS` provides a path, use it as `--repo`.
   - Otherwise default to the current working directory.

2. Run:
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/src/open_context/cli.py" architecture validate \
     --repo <repo-root>
   ```
   If `$ARGUMENTS` includes a subdirectory to limit the scan (e.g. `app/operations/v1/bookings`), add `--path <subdir>`.

3. Show the full output: which rules fired, which files violated them, severity, and guidance for each violation.

## Rules checked

| Rule | Detects |
|------|---------|
| R1 | AR queries or `raise` inside controller action methods |
| R2 | `Form.new()` not followed by `.valid!` |
| R3 | `Form.new(params)` instead of `permit_params` |
| R4 | `render json:` instead of `render_json()` |
| R5 | Unscoped `Model.find(params[:id])` on tenant-scoped resources |
| R6 | Bare `raise "string"` instead of a custom exception class |

> This command runs grep across the real codebase. Use for compliance checks, not as a routine command.
