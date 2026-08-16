# Open:Context — Library API: Context Decisions

Governance record for `context.yaml`. Operational content stays in context.yaml;
justifications and dropped decisions live here.

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
| `catalog_management` | `routing_only` | Standard CRUD — convention-following, no surprising patterns; file paths inferrable from naming convention alone |
| `borrowing_management` | `file_indexed` | Concurrency requirement (`with_lock` for copy inventory) + multi-step checkout flow = non-obvious implementation; explicit file list prevents guessing wrong paths |
| `member_management` | `file_indexed` | Member search requires pagination knowledge that isn't inferrable from naming; subtype adds cross-cutting pattern |

## Dropped Rules Log

No rules dropped — 6 rules fit within the 8-rule budget for this example.

## Justification Changelog

**`atomic_copy_decrement` pattern** (borrowing_management → checkout_copy subtype)
- Why it belongs: copy_count check and decrement are NOT atomic by default — classic TOCTOU. Two patrons checking out the last copy simultaneously will both read count=1 and both succeed.
- Generalizes to: any "check-then-act" on shared counters (inventory, quota, seats).
- Evidence: 2 incidents in comparable projects where oversell occurred without locking.
- Cost: Must be taught explicitly; not inferrable from HMVC convention alone.

**`paginate_member_list` pattern** (member_management → member_search subtype)
- Why it belongs: Rails default returns unbounded result sets; `search_member` endpoints target open-ended patron lists.
- Evidence: Standard Rails footgun; no project-specific incident but universal risk.
- Cost: One-liner rule, low noise, high return.

## Extra Components Design Decision

`borrowing_management` uses `extra_components: [record_lock]` to add `record_lock`
to the component chain when a borrowing task is resolved. This replaces what would
otherwise be a hardcoded domain name check in the resolver (`if "borrowing_management"...`).

**Principle:** Domain-specific component requirements belong in the context model (data),
not in the resolver (mechanism). The resolver reads `extra_components` from matched
domains and appends them to the flow generically.
