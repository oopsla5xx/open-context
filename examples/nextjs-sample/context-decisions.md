# Open:Context — Task Tracker (Next.js): Context Decisions

Governance record for `context.yaml`. Operational content stays in context.yaml;
justifications and dropped decisions live here. Structure mirrors
`examples/rails-hmvc-sample/context-decisions.md` — this sample exists specifically
to test whether that concept (LLM-generated context.yaml + written rationale)
holds up on a second framework. See `docs/nextjs-effectiveness-report.md`.

## Knowledge Budget

| Layer | Limit | Used |
|-------|-------|------|
| L1 Stack | 1 project block | 1 ✓ |
| L2 Architecture | 5 component types | 4 (no `interaction` layer — simple project) |
| L3 Domains | ≤8 | 3 ✓ |
| L4 Invariants | ≤8 | 6 ✓ |
| Patterns per domain | ≤4 | ≤2 ✓ |
| Subtypes per domain | ≤3 | ≤2 ✓ |

## Coverage Level Rationale

| Domain | Level | Reason |
|--------|-------|--------|
| `project_management` | `routing_only` | Standard CRUD — file paths inferrable from the Server Action naming convention alone (`app/projects/actions.ts`), no surprising patterns |
| `task_management` | `file_indexed` | Kanban ordering + assignment logic isn't inferable from naming; explicit file list prevents guessing wrong paths |
| `team_billing` | `pattern_indexed` | TOCTOU-safe usage check and the owner-only plan-change guard are non-obvious — must be taught explicitly, not convention-following |

## Dropped Rules Log

No rules dropped — 6 rules fit within the 8-rule budget for this example.

## Justification Changelog

**`atomic_usage_limit_check` pattern** (team_billing)
- Why it belongs: checking `usageCount < usageLimit` and then incrementing as two
  separate statements is a classic check-then-act race — two concurrent Stripe
  webhook deliveries can both read "under limit" and both write, pushing the team
  over its cap. Same category as the Rails sample's `atomic_copy_decrement`, just a
  different concurrency primitive (`prisma.$executeRaw` with the check folded into
  the WHERE clause, vs. Rails' `with_lock`).
- Generalizes to: any check-then-act on a shared counter (inventory, quota, seats,
  usage limits).
- Evidence: runtime-verified in Task 7 with a disposable probe script — an
  over-limit request was correctly rejected, an under-limit request correctly
  applied and incremented atomically.
- Cost: must be taught explicitly; a developer reaching for the obvious
  `findUnique` → check → `update` sequence would reintroduce the race.

**`owner_only_plan_change` pattern** (team_billing)
- Why it belongs: per Next.js's own Data Security guidance (verified in Task 4),
  framework-level CSRF checks are not an authorization boundary — every Server
  Action is a POST endpoint reachable directly, not just through the UI. Billing
  plan changes need an explicit actor check inside the action.
- Generalizes to: any Server Action gating a destructive or privileged mutation.
- Evidence: Next.js docs (`guides/server-actions.md`, `guides/data-security.md`)
  explicitly warn against relying on render-time gating alone.
- Cost: one-line guard (`requireOwner(actorRole)`), low noise, high return.

**`atomic_reorder_shift` pattern** (task_management → task_reordering subtype)
- Why it belongs: moving a task between kanban columns isn't a single-field
  update — every task already in the destination column at or after the drop
  position must shift by one, or two concurrent drags collide on the same `order`
  value.
- Generalizes to: any position-based reordering over a shared ordinal column.
- Evidence: implemented and type-checked in Task 6 (`lib/services/task-service.ts`,
  wrapped in `prisma.$transaction`). Not runtime-probed the way billing was — lower
  blast radius (a UI glitch, not a financial/security issue) didn't justify the
  same verification cost.
- Cost: needs a transaction, not obvious from a plain CRUD mental model of "update
  one row."

## Extra Components Design Decision

`team_billing` uses `extra_components: [route_handler]` to add `route_handler` to
the component chain when a billing task is resolved. Stripe delivers usage events
via webhook POST, not through a user-invoked Server Action — `route_handler` is a
different Next.js primitive from the rest of `architecture.flow` (which is
Server-Actions-first). Same principle as the Rails sample's `record_lock` decision:
domain-specific component requirements belong in the context model (data), not as
a hardcoded domain-name check in the resolver.

## Component Naming Decision — `prisma_model`, then reverted to `model` (RESOLVED)

**Update:** `component_reason()` was made data-driven — see below. The component
is named `model` again as of that fix. The rest of this section is kept as the
historical record of why the workaround existed.

The persistence component in `architecture.flow` was temporarily named `prisma_model`
instead of the more obvious `model`. This was a deliberate workaround, not a naming
preference:

- **Finding:** `resolver.py`'s `component_reason()` (lines 240–270) hardcodes
  Rails-flavored descriptions keyed on the literal component names `controller`,
  `operation`, `form`, `model`, `serializer` — the `model` entry's text references
  `ApplicationForm` and `attr_reader`, Ruby/Rails APIs. Using `model` here collided
  with that dict and silently injected Rails-specific text into Next.js task
  output, discovered while verifying a `resolve` smoke test against this sample.
- **Decision:** rename the component in this `context.yaml` rather than fix
  `resolver.py` immediately. A real fix would make `component_reason()`
  data-driven (read descriptions from `context.yaml` instead of a hardcoded
  dict) — a genuine refactor, deliberately deferred to keep the original
  benchmark phase measurement-only (see `docs/nextjs-effectiveness-report.md`).
- **Consequence:** this was the headline finding of the benchmark, written up in
  `docs/nextjs-effectiveness-report.md` — the resolver was not yet as fully
  framework-agnostic as its own docstrings claim.
- **Resolution:** `component_reason()` (`resolver.py`) was rewritten to derive its
  text from `context.yaml`'s own `components.<name>.responsibility`/`patterns` —
  no framework-specific dict remains. Verified with a new test
  (`test_component_reason_reads_from_context_not_hardcoded_rails_text` in
  `tests/test_hook_integration.py`) asserting a component named `model` in a
  non-Rails project's `context.yaml` never surfaces Rails-specific text. The
  component here was renamed back to `model`.
