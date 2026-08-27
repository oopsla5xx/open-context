# Open:Context — Analytics Pipeline: Context Decisions

Governance record for `context.yaml`. Operational content stays in
context.yaml; justifications and dropped decisions live here. Structure
mirrors `examples/rails-hmvc-sample/context-decisions.md` — this sample
exists to demonstrate the no-layer case: a repo with no controller/model
architecture, where `architecture.flow` is legitimately absent rather than
forced into a fake layered shape.

## Knowledge Budget

| Layer | Limit | Used |
|-------|-------|------|
| L1 Stack | 1 project block | 1 ✓ |
| L2 Architecture | 5 component types | 0 (no layered architecture — see below) |
| L3 Domains | ≤8 | 2 ✓ |
| L4 Invariants | ≤8 | 2 ✓ |

## Why `architecture.flow` is absent

This repo is a set of standalone scripts (`scripts/ingest/`,
`scripts/reports/`) each run on a schedule, not a web app with request/
response layering. Forcing a `controller → model`-style flow onto it
would misdescribe the codebase — there is no request entry point, no
persistence layer distinct from the script itself. `context.yaml` omits
L2 entirely; domains still route on keywords/related_components/patterns
without it (`architecture.flow` is optional in schema.py as of the
docs-first pivot — see `tasks/plan.md`).

## Coverage Level Rationale

| Domain | Level | Reason |
|--------|-------|--------|
| `data_ingestion` | `pattern_indexed` | Idempotency requirement isn't inferrable from a script's name alone — must be taught explicitly |
| `report_generation` | `pattern_indexed` | Caching-before-export requirement isn't inferrable from convention — must be taught explicitly |

## Dropped Rules Log

No rules dropped — 2 rules fit within the 8-rule budget for this example.

## Justification Changelog

**`idempotent_ingestion` pattern** (data_ingestion)
- Why it belongs: source `docs/rules/ingestion-checklist.md` — the scheduler
  retries failed runs automatically, so a plain append-only insert on retry
  creates duplicate rows: a silent data-correctness bug, not a visible crash.
- Source file: `docs/rules/ingestion-checklist.md` (read verbatim, not
  inferred from code — this example demonstrates the docs-first path).
- Generalizes to: any scheduled job with automatic retry writing to a
  shared store.

**`cache_before_export` pattern** (report_generation)
- Why it belongs: source `AGENTS.md` — re-aggregating from raw rows on every
  manual report re-run is both slow and non-deterministic if upstream data
  changed in the meantime.
- Source file: `AGENTS.md` (read verbatim).
- Generalizes to: any manually-triggered report/export over a large or
  slow-changing dataset.

## Traceability note

Every rule and pattern in `context.yaml` carries a `source:` field citing
the doc it was read from (`AGENTS.md` or `docs/rules/ingestion-checklist.md`
in this repo) — this is the docs-first synthesis path, not the code-reading
fallback (which would cite a code file instead).
