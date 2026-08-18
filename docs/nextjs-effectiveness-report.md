# Next.js Effectiveness Benchmark — Report

Sample: `examples/nextjs-sample/`

## Summary

The resolver engine (`resolver.py`) routes correctly on a Next.js App Router /
Server Actions stack — phrasing coverage, amplification safety, and
cross-domain co-routing all behave the way the Rails reference sample
predicts. But the benchmark did not just measure the resolver; it also
exercised code paths the Rails sample never touches, and that surfaced two
real defects in the engine's claim to be framework-agnostic. One was a
one-line bug, fixed. The other is a genuine design gap — a hardcoded,
Rails-flavored fallback table inside `component_reason()` — worked around at
first, then fixed (see Finding 1 below). That gap was the headline result of
this benchmark, not a footnote.

**Verdict:** resolver routing logic — pass. "Resolver is generic" as
currently documented — not fully true; corrected below.

## Method

A real, buildable Next.js 16.3.1 skeleton (`.tmp-nextjs-sample/`, disposable,
deleted after this report and after user review) implementing a 3-domain SaaS
task tracker; `context.yaml` generated via a real `/oc-setup` run against it;
benchmarked against the same coverage/amplification/file-existence checks the
Rails sample is held to, plus 6 fixed prompt scenarios (5 positive, 1 negative
control) measuring injected-context size against a full-context baseline.

## Results

### Phrasing coverage + amplification (`open-context validate --repo --strict`, exit 0)

| Domain | Coverage | Risk |
|---|---|---|
| `project_management` | 100% (10/10) | LOW |
| `task_management` | 100% (10/10) | LOW |
| `team_billing` | 80% (8/10) | LOW |
| **Total** | **93.3% (28/30)** | |

Pass against the ≥80%/domain, 0-domains-HIGH threshold. One
amplification WARNING (not HIGH): `project_management`, token `project`
matches 4 keywords (`project`, `projects`, and the underscore-parts of
`create_project`/`delete_project`).

`team_billing`'s two failures ("check the team usage limit", "review the
latest invoice") both matched exactly one keyword. The resolver's routing
threshold is `max(2, top_score × 0.66)` — a single-keyword hit with no
competing domain never clears it. This is the resolver behaving exactly as
designed, confirmed against a second framework; it was not patched to inflate
the coverage number.

File existence (`--repo .tmp-nextjs-sample/`): 8/8 declared `related_components`
paths found in the real skeleton. 0 missing.

### Token reduction (6 fixed scenarios, full-context baseline = 4751 bytes)

| # | Prompt | Matched domain(s) | Injected | Reduction |
|---|---|---|---|---|
| 1 | "add task assignment to a project" | `project_management` + `task_management` | 2585 B | 45.6% |
| 2 | "fix billing webhook race condition" | `team_billing` | 4192 B | 11.8% |
| 3 | "list projects for owner" | `project_management` | 1919 B | 59.6% |
| 4 | "rename a project" | `project_management` | 1951 B | 58.9% |
| 5 | "reorder tasks in the kanban board" | `task_management` | 2740 B | 42.3% |
| 6 | "explain what this error means" (negative control) | none | 0 B | 100% |

**Average across scenarios 1–5: 43.6%.**

Two things this number needs, or it misleads:

- **It is not comparable to the README's 91% figure**, and shouldn't be read
  as "Next.js underperforms Rails." The 91% figure came from a production
  Rails codebase (~2,000 files, 8 domains); this sample has 3 domains by
  deliberate design, mirroring the Rails *example*'s Knowledge Budget
  discipline, not a production codebase. Reduction % is a function of how
  much bigger the full context is than any one domain — a small `context.yaml`
  has a small full-context baseline, so there's less to reduce.
- **Scenario 2's 11.8% is explained, not a resolver weakness.** `team_billing`
  is `pattern_indexed` with 2 patterns, 5 related files, and 2 domain-scoped
  rules — by construction, the single biggest contributor to this sample's
  full-context size. Matching it alone barely reduces size because it *is*
  most of the size. This would look different in a larger project where
  `team_billing`-sized domains are a smaller fraction of the whole.
- **Scenario 1 co-routed two domains** instead of the one I'd originally
  annotated. Not a failure: the phrasing genuinely names both a task and its
  parent project, and cross-domain co-routing is documented, intended
  behavior (mirrors hypothesis H4 in `docs/open-context-v0-architecture.md`).
- **Scenario 6 (negative control) passed cleanly** — no domain matched, zero
  bytes injected, not an empty report.

## Findings beyond the numbers

### Finding 1 (headline) — the resolver is not fully framework-agnostic yet [FIXED]

> **Update:** fixed after this report was written. `component_reason()` is now
> data-driven — see the note at the end of this section. Left the original
> writeup below intact as the record of what was found and why it mattered.

`resolver.py`'s `component_reason()` (lines 240–270) hardcodes human-readable
component descriptions keyed on the literal Rails component names
`controller`/`operation`/`form`/`model`/`serializer` — including references to
`ApplicationForm` and `attr_reader`, Ruby/Rails APIs. This directly contradicts
the module's own docstring claim ("the resolver is generic — it does NOT
contain framework-specific logic").

It surfaced because this sample's persistence component was naturally named
`model` — the obvious name — and collided with the dict, silently injecting
Rails-specific text into Next.js task output. **Scope decision for this
phase:** rather than refactor `component_reason()` into something data-driven
(reading descriptions from `context.yaml`), the sample's component was renamed
to `prisma_model` to route around the collision (see
`examples/nextjs-sample/context-decisions.md` → "Component Naming Decision").
That refactor is real engine work, correctly out of scope for a
measurement-only phase — but it should not be filed away. It is the single
most important thing this benchmark found: **the "generic resolver" claim in
`__init__.py`/`resolver.py`'s docstrings is currently aspirational for any
component name that happens to match one of the 5 hardcoded Rails keys**
(`controller`, `operation`, `form`, `model`, `serializer`). A project using any
of those 5 names for a non-Rails architecture will hit the same silent
collision this sample did.

**Recommendation:** a follow-up phase to make `component_reason()` read from
`context.yaml` (e.g., a per-component `description` field, falling back to the
generic message), gated on `architecture.name == "HMVC"` or similar, so the
Rails-specific text only appears for Rails-shaped projects.

**Resolution:** `component_reason()` no longer contains any hardcoded dict.
It derives its text from `context.yaml`'s own `components.<name>.responsibility`
and `.patterns` — the same fields every example (Rails and Next.js) already
declares — falling back to the original generic message
(`"'<comp>' is part of the architecture flow for this task."`) when a component
has neither. No gating on `architecture.name` was needed: the Rails sample's own
`context.yaml` already carries enough `responsibility`/`patterns` content to
produce equally informative (in fact more accurate, since it's not hand-authored
prose divorced from the actual context.yaml) text without any hardcoded branch.
`examples/nextjs-sample/context.yaml`'s persistence component has been renamed
back to `model` — the collision this section describes no longer occurs.
Verified with `tests/test_hook_integration.py::test_component_reason_reads_from_context_not_hardcoded_rails_text`.

### Finding 2 (fixed during this phase) — `.ts`/`.tsx` files misclassified as directories

`resolver.py`'s file-inference classifier recognized `.rb`/`.py`/`.js` as
"specific file" suffixes but not `.ts`/`.tsx`. Every TypeScript path in this
sample's `related_components` was falling through to the "search this
directory" branch and getting a hardcoded Ruby naming hint
(`create_operation.rb / create_form.rb`) attached — nonsensical for a
TypeScript file. Fixed (commit "open-context(fix): recognize .ts/.tsx as
specific files..."), verified via `pytest` (17/17 still pass) and a `resolve`
re-run showing clean output. One-line-per-site fix; approved as in-scope
because it's an unambiguous bug, not a design question.

### Finding 3 — cosmetic wording was easy to fix; the underlying claim needed a caveat

A first pass reworded `__init__.py`/`cli.py`/`resolver.py` docstrings and the
CLI's top-level description away from "Rails HMVC" framing. That was the easy
part.
Finding 1 above shows the *code*, not just the wording, still has Rails
assumptions baked in — a reminder that a docstring rewrite can make a claim
sound truer than it is.

### Known limitation (unchanged, explicitly confirmed) — `architecture validate` is Rails-only

`validator.py`'s 6-rule static analyzer (R1–R6) is Ruby/Rails-syntax regex —
genuinely Rails-only, not a generalization gap the same way Finding 1 is. This
phase did not attempt to change it, and the `architecture validate` subcommand's
CLI help text was deliberately left describing it as Rails-specific, because
that's accurate. No new information here beyond confirming the
existing README "Limitations" section is still correct.

## Success criteria

- [x] `examples/nextjs-sample/context.yaml` + `tests/*.txt` generated by a real `/oc-setup` run
- [x] `examples/nextjs-sample/context-decisions.md` follows the Rails sample's format
- [x] `.tmp-nextjs-sample/` built successfully (`npm run build` exit 0) at the time `validate --repo` ran against it
- [x] Coverage %, amplification risk, token-reduction % (per-scenario + average) all reported above, pass/fail stated plainly
- [x] Cosmetic wording changes land, `tests/test_hook_integration.py` still passes (17/17)
- [x] `validator.py`'s Rails-only scope explicitly confirmed, not silently omitted
- [x] `.tmp-nextjs-sample/` deleted after user review

## Recommendation

Don't add Next.js to the README's supported-framework list yet — that
decision is deferred until after this report is reviewed. Finding 1 is now
fixed (see the resolution note in that
section) — the resolver's "generic, no framework-specific logic" claim in
`__init__.py`/`resolver.py` is accurate again. A related, more impactful gap
surfaced afterward by a separate real-world test — see
`docs/nextjs-real-world-test-report.md`, Finding A — remains open.
