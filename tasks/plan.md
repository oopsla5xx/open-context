# Implementation Plan: Docs-first, any-repo generalization

## Overview

Open:Context pivots from "Rails/HMVC architecture-aware" to "any repo, any
language" by splitting doc discovery into two distinct concerns (mirroring
the 4a-code vs 4b-LLM split already applied elsewhere): a deterministic glob
that lists `README.md`/`CLAUDE.md`/`AGENTS.md`/`docs/**/*.md` (no LLM), and
the existing agentic `/oc-setup` synthesis step, now required to read those
docs first, fall back to reading source code directly when no docs exist,
and cite a `source:` file for every rule/pattern it writes. Rails-only
tooling (4b architecture discovery, HMVC R1-R6 validator) is removed
entirely rather than kept as a special case. Decisions below were reached in
a `/grill-me` session — see that conversation for the full rationale; this
plan does not re-litigate them.

## Architecture Decisions

- **4b (`architecture_discovery.py`) and the HMVC R1-R6 validator are
  deleted, not deprecated.** Confirmed via grep: no other module imports
  from `architecture_discovery.py`; `resolver.py` and `test_hook_integration.py`
  only use the generic `architecture:`/`flow` YAML key, never the Rails
  discovery module. Safe to remove without touching the resolver's core
  algorithm.
- **`docs_discovery.py` is a new module**, not an extension of
  `discovery.py` — discovery.py's job (structured-manifest stack detection)
  and docs_discovery.py's job (file listing) are different in kind, same
  reasoning as why 4a and 4b were already separate modules.
- **`resolver.py:474`** (`context["architecture"]["flow"]`) is a confirmed
  hard dependency on `architecture.flow` existing — this KeyErrors today if
  the key is absent. PR4 must patch this alongside the schema relaxation, or
  the schema change ships a state the resolver can't actually run against.
- **Source-of-truth for `source:` backfill on existing examples** is
  `context-decisions.md` (already exists per example, contains a
  "Justification Changelog" with evidence per pattern) — no new research
  needed, just structured extraction.
- `run_arch_validate` is re-exported from `src/open_context/__init__.py:12,24`
  — deleting `validator.py`'s HMVC section requires updating this export
  list too, or `__init__.py` breaks on import.

## Task List

### Phase 1: Remove Rails-only tooling (PR1)
- [ ] Task 1: Delete 4b architecture discovery module and its tests
- [ ] Task 2: Delete HMVC R1-R6 validator and its CLI/skill surface
- [ ] Task 3: Sweep docs/CLAUDE.md references to removed features

### Checkpoint: PR1 complete
- [ ] `pytest tests/ -v` passes with zero references to `architecture_discovery`/`run_arch_validate`/HMVC left in source
- [ ] `open-context --help` no longer lists `architecture` subcommand
- [ ] Review with human before proceeding to PR2

### Phase 2: Deterministic doc discovery (PR2)
- [ ] Task 4: Implement `docs_discovery.py`
- [ ] Task 5: Wire `discover-docs` CLI subcommand
- [ ] Task 6: Unit tests for `docs_discovery.py`

### Checkpoint: PR2 complete
- [ ] `pytest tests/test_docs_discovery.py -v` passes
- [ ] `open-context discover-docs --repo examples/rails-hmvc-sample --json` returns real output
- [ ] Review with human before proceeding to PR3

### Phase 3: Expand stack detection (PR3)
- [ ] Task 7: Add Go detector (`go.mod`)
- [ ] Task 8: Add Rust detector (`Cargo.toml`)
- [ ] Task 9: Add Java detector (`pom.xml` / `build.gradle`)

### Checkpoint: PR3 complete
- [ ] `pytest tests/test_discovery.py -v` passes, including new Go/Rust/Java cases
- [ ] `detect()` output for each new ecosystem follows the existing `{value, confidence, source}` shape, never blended into one score
- [ ] Review with human before proceeding to PR4

### Phase 4: Schema traceability + flow relaxation (PR4)
- [ ] Task 10: Add mandatory `source:` validation for `rules[]` and `domains[].patterns[]`
- [ ] Task 11: Make `architecture.flow` optional in schema + patch resolver's hard dependency
- [ ] Task 12: Backfill `source:` on the two existing examples
- [ ] Task 13: Add a new no-layer example

### Checkpoint: PR4 complete
- [ ] `pytest tests/ -v` passes
- [ ] `open-context validate --context examples/rails-hmvc-sample/context.yaml --tests examples/rails-hmvc-sample/tests/` still passes after backfill
- [ ] `open-context validate --context <new-example>/context.yaml` passes with empty/absent `architecture.flow`
- [ ] Review with human before proceeding to PR5

### Phase 5: Wizard flow rewrite (PR5)
- [ ] Task 14: Rewrite `/oc-setup` Phase 0/1 into docs-first single-confirm flow
- [ ] Task 15: Rewrite `/oc-init` to use the same docs-first logic
- [ ] Task 16: Update CLAUDE.md to reflect the new architecture

### Checkpoint: PR5 complete / final verification
- [ ] Run `/oc-setup` on ≥1 real repo with good docs (e.g. this repo itself, or `examples/rails-hmvc-sample`) — confirm generated `context.yaml` has correct `source:` citations
- [ ] Run `/oc-setup` on ≥1 real repo with no AGENTS/CLAUDE/README docs — confirm the code-reading fallback still produces a usable `context.yaml`
- [ ] `open-context validate` passes on both generated files
- [ ] All acceptance criteria across PR1-PR5 met

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| `resolver.py:474` KeyErrors once `architecture.flow` becomes optional | High — breaks resolve() for any context.yaml without a flow | Task 11 patches the exact line with a `.get(..., [])` fallback before the schema is relaxed |
| Deleting HMVC validator silently breaks `__init__.py` import | Medium — `from open_context import run_arch_validate` starts failing at import time for any external consumer | Task 2 explicitly updates `__init__.py`'s import/`__all__` list, not just `validator.py` |
| PR2's docs glob picks up huge doc trees in large monorepos (perf) | Low-Medium | Hardcoded ignore list (node_modules/vendor/.git/dist/build/.open-context) agreed in grill-me; Task 4 must implement it, not defer it |
| PR5's "LLM reads code directly" fallback has no automated test (not deterministic) | Medium — regressions here are silent | Final checkpoint's real-repo dry run is the deliberate verification method (agreed in grill-me over adding brittle golden-file tests) |
| Backfilling `source:` on existing examples (Task 12) misattributes a pattern to the wrong file | Low | Cross-check each backfilled `source:` against the actual "evidence" line in that example's `context-decisions.md`, not guessed |

## Open Questions

None outstanding — all resolved in the preceding `/grill-me` session. If PR4's Task 11 turns up additional `architecture["flow"]` call sites beyond `resolver.py:474` during implementation, flag before proceeding rather than patching silently.
