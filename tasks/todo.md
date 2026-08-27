# Task List: Docs-first, any-repo generalization

See `tasks/plan.md` for overview, architecture decisions, risks. Tasks are
grouped into 5 PRs, in dependency order: PR1 → PR2 → PR3 → PR4 (needs PR2's
`discover-docs` output shape) → PR5 (needs PR2 + PR4).

---

## PR1 — Remove Rails-only tooling

### Task 1: Delete 4b architecture discovery module and its tests

**Description:** Remove `architecture_discovery.py` (Phase 4b, Rails-only
component-chain discovery) and its dedicated test file. Confirmed via grep
that no other module imports from it — `resolver.py` only reads the generic
`architecture.flow` YAML key, never this module.

**Acceptance criteria:**
- [x] `src/open_context/architecture_discovery.py` deleted
- [x] `tests/test_architecture_discovery.py` deleted
- [x] `grep -rn "architecture_discovery" src/ tests/` returns nothing

**Verification:**
- [x] Tests pass: `/usr/bin/env python3 -m pytest tests/ -v`
- [x] Manual check: `python3 -c "import open_context"` still succeeds (no dangling import)

**Dependencies:** None

**Files likely touched:**
- `src/open_context/architecture_discovery.py` (delete)
- `tests/test_architecture_discovery.py` (delete)

**Estimated scope:** Small: 1-2 files

---

### Task 2: Delete HMVC R1-R6 validator and its CLI/skill surface

**Description:** Remove the "Architecture rules (6 HMVC compliance checks)"
section of `validator.py` (lines ~269 to end — `R1`-`R6` regex patterns,
`_r1_check`...`_r6_check`, `run_arch_validate` and its helpers), the
`architecture validate`/`architecture discover` CLI subcommands
(`cmd_arch_validate`, `cmd_arch_discover`, and the `p_arch`/`arch_sub`
parser block in `cli.py`), and the `.claude/skills/oc-validate-architecture/`
skill directory. Update `src/open_context/__init__.py` — it currently
imports and re-exports `run_arch_validate` (lines 12, 24); both must be
removed or `import open_context` breaks.

**Acceptance criteria:**
- [x] `validator.py` no longer contains the HMVC rules section or `run_arch_validate`
- [x] `cli.py` no longer has an `architecture` subcommand (neither `validate` nor `discover`)
- [x] `.claude/skills/oc-validate-architecture/` deleted
- [x] `__init__.py` import list and `__all__` no longer reference `run_arch_validate`

**Verification:**
- [x] Tests pass: `/usr/bin/env python3 -m pytest tests/ -v`
- [x] Manual check: `open-context --help` (or `python3 -m open_context.cli --help`) shows no `architecture` subcommand
- [x] Manual check: `python3 -c "from open_context import validate_context, run_phrasing_tests, run_amplification_checks, detect"` succeeds

**Dependencies:** None (independent of Task 1, can run in parallel within PR1)

**Files likely touched:**
- `src/open_context/validator.py`
- `src/open_context/cli.py`
- `src/open_context/__init__.py`
- `.claude/skills/oc-validate-architecture/` (delete dir)
- `tests/test_hook_integration.py` (remove any `architecture validate`/`architecture discover` CLI-boundary tests if present — confirm via grep first, don't assume)

**Estimated scope:** Medium: 3-5 files

---

### Task 3: Sweep docs/CLAUDE.md references to removed features

**Description:** Remove or rewrite mentions of 4b, `architecture discover`,
`architecture validate`, HMVC R1-R6, and `/oc-validate-architecture` across
`CLAUDE.md`, `docs/open-context-v0-architecture.md`, `docs/reference.md`,
`README.md`, `README.vi.md`. This is a docs-only cleanup — don't rewrite
sections unrelated to the removed features (e.g. `docs/nextjs-effectiveness-report.md`
and `docs/nextjs-real-world-test-report.md` are historical benchmark
reports; leave their content as-is, just note removal doesn't retroactively
invalidate them if they mention 4b only as historical context — check case
by case).

**Acceptance criteria:**
- [x] `grep -rn "architecture_discovery\|arch_discover\|arch_validate\|HMVC\|oc-validate-architecture" CLAUDE.md docs/ README.md README.vi.md` returns nothing (or only inside clearly-historical report files, judged case by case) — remaining hits are `docs/open-context-v0-architecture.md`/`docs/nextjs-effectiveness-report.md` (historical reports, left as-is) and standalone "HMVC" as one architecture-pattern choice label, not the deleted validator
- [x] CLAUDE.md's "Repository Layout", "Plugin Architecture", "Skills", "Phase 4" sections no longer describe 4b/HMVC as current features

**Verification:**
- [x] Manual check: read through CLAUDE.md top to bottom, confirm it accurately describes the post-PR1 codebase (no dangling references)
- [x] Also patched `.claude/skills/oc-setup/SKILL.md` (out of the original file list, but necessary — Phase 0 was invoking the now-deleted `architecture discover` CLI command; left unpatched, running `/oc-setup` today would break). Question 4 now always asks blind; full docs-first rewrite deferred to PR5 (Task 14) as planned.

**Dependencies:** Task 1, Task 2 (needs to know exactly what was removed before describing what remains)

**Files likely touched:**
- `CLAUDE.md`
- `docs/open-context-v0-architecture.md`
- `docs/reference.md`
- `README.md`, `README.vi.md`

**Estimated scope:** Medium: 3-5 files

---

## Checkpoint: PR1 complete
- [x] `/usr/bin/env python3 -m pytest tests/ -v` passes (42/42)
- [x] Zero source/doc references to `architecture_discovery`, `run_arch_validate`, HMVC R1-R6 remain (except judged-historical report content)
- [ ] Review with human before starting PR2

---

## PR2 — Deterministic doc discovery (Việc 1)

### Task 4: Implement `docs_discovery.py`

**Description:** New module implementing a pure, deterministic (no LLM)
recursive file listing: exact filenames `README.md`/`CLAUDE.md`/`AGENTS.md`
at any directory depth, plus every `.md` file under any `docs/` directory
(`docs/**/*.md`). Skip `node_modules`, `vendor`, `.git`, `dist`, `build`,
`.open-context` directories entirely (don't descend into them — for
performance, not just filtering results after the fact). Match the
`{value, confidence, source}`-free, plain-list output style of Phase 4a's
non-blended philosophy: this returns a flat, deterministic list, not a
scored/confidence result (there's nothing uncertain about "this file
exists").

**Acceptance criteria:**
- [x] `discover_docs(repo: Path) -> dict` returns e.g. `{"repo": str, "docs_found": [{"path": "app/policies/AGENTS.md", "kind": "AGENTS.md"|"CLAUDE.md"|"README.md"|"docs_md"}, ...]}`
- [x] Ignored directories are never descended into (verify with a test asserting a `node_modules/README.md` is absent from results, not just filtered post-hoc)
- [x] Case-insensitive filename matching for the 3 fixed names (mirrors the user's original `find -iname` proposal)

**Verification:**
- [x] Tests pass: `/usr/bin/env python3 -m pytest tests/test_docs_discovery.py -v`
- [x] Manual check: ran against this repo itself — `context-decisions.md`-type files correctly not picked up (matches neither the 3 fixed names nor `docs/**/*.md`)

**Dependencies:** None (independent of PR1)

**Files likely touched:**
- `src/open_context/docs_discovery.py` (new)

**Estimated scope:** Small: 1 file

---

### Task 5: Wire `discover-docs` CLI subcommand

**Description:** Add `open-context discover-docs --repo <path> --json` to
`cli.py`, following the exact pattern of `cmd_detect`/`p_detect` (the 4a
CLI wiring) — same `--repo` arg, same `--json` flag behavior, same exit-code
conventions.

**Acceptance criteria:**
- [x] `open-context discover-docs --repo <path>` prints human-readable output
- [x] `open-context discover-docs --repo <path> --json` prints valid JSON matching Task 4's shape
- [x] `open-context --help` lists the new subcommand

**Verification:**
- [x] Tests pass: `/usr/bin/env python3 -m pytest tests/ -v` — confirmed `test_hook_integration.py` only subprocess-tests the 3 hooks, never CLI subcommands (not even `detect`), so no subprocess test added for `discover-docs` either, matching existing convention
- [x] Manual check: `open-context discover-docs --repo . --json` returns valid JSON

**Dependencies:** Task 4

**Files likely touched:**
- `src/open_context/cli.py`

**Estimated scope:** Small: 1 file

---

### Task 6: Unit tests for `docs_discovery.py`

**Description:** Direct-import unit tests (not subprocess), following
`tests/test_discovery.py`'s established convention (`PLUGIN_ROOT` sys.path
setup, `tmp_path` fixtures for synthetic repo trees). Cover: no docs found,
all 3 fixed names at various depths, `docs/**/*.md` including nested dirs
(e.g. `docs/rules/security-checklist.md`), ignored-directory exclusion
(`node_modules/README.md` must not appear), case-insensitivity.

**Acceptance criteria:**
- [x] `tests/test_docs_discovery.py` exists, follows `test_discovery.py`'s header/import style
- [x] At least one test per: empty repo, nested AGENTS.md, `docs/rules/*.md`, ignored-dir exclusion, case-insensitive match (8 tests total, includes the `context-decisions.md` boundary check too)

**Verification:**
- [x] Tests pass: `/usr/bin/env python3 -m pytest tests/test_docs_discovery.py -v` (8/8)

**Dependencies:** Task 4

**Files likely touched:**
- `tests/test_docs_discovery.py` (new)

**Estimated scope:** Small: 1 file

---

## Checkpoint: PR2 complete
- [x] `/usr/bin/env python3 -m pytest tests/ -v` passes (50/50, full suite)
- [x] `open-context discover-docs --repo . --json` returns real, correct output
- [ ] Review with human before starting PR3

---

## PR3 — Expand stack detection (4a)

### Task 7: Add Go detector (`go.mod`)

**Description:** `detect_go(repo: Path) -> dict | None` in `discovery.py`,
following `detect_ruby`/`detect_node`/`detect_python`'s exact shape: each
field wrapped via the existing `_field(value, confidence, source)` helper,
never blended into one score. Parse `go.mod` for module name and Go
version directive; detect common frameworks (e.g. `gin-gonic/gin`,
`labstack/echo`, `gofiber/fiber`) from `require` lines if present, same
confidence-tiering pattern as `_NODE_FRAMEWORKS`.

**Acceptance criteria:**
- [x] `detect_go()` returns `None` when no `go.mod` present
- [x] Returns `{"language": _field("Go", ...), "language_version": _field(...), ...}` shape matching existing ecosystems
- [x] Wired into `detect()`'s ecosystem list

**Verification:**
- [x] Tests pass: `/usr/bin/env python3 -m pytest tests/test_discovery.py -v`

**Dependencies:** None (independent of PR1/PR2)

**Files likely touched:**
- `src/open_context/discovery.py`

**Estimated scope:** Small: 1 file

---

### Task 8: Add Rust detector (`Cargo.toml`)

**Description:** `detect_rust(repo: Path) -> dict | None`, same shape as
Task 7. Parse `Cargo.toml` `[package]` for name/edition/rust-version,
`[dependencies]` for common frameworks (`actix-web`, `axum`, `rocket`).

**Acceptance criteria:**
- [x] `detect_rust()` returns `None` when no `Cargo.toml` present
- [x] Returns `{value, confidence, source}`-shaped fields matching existing ecosystems
- [x] Wired into `detect()`'s ecosystem list

**Verification:**
- [x] Tests pass: `/usr/bin/env python3 -m pytest tests/test_discovery.py -v`

**Dependencies:** None

**Files likely touched:**
- `src/open_context/discovery.py`

**Estimated scope:** Small: 1 file

---

### Task 9: Add Java detector (`pom.xml` / `build.gradle`)

**Description:** `detect_java(repo: Path) -> dict | None`, same shape as
Task 7. Two build-tool variants to parse (Maven's `pom.xml` XML,
Gradle's `build.gradle`/`build.gradle.kts`) — detect which is present,
extract group/artifact/Java version where available, detect
Spring Boot/Ktor from dependency declarations.

**Acceptance criteria:**
- [x] `detect_java()` returns `None` when neither `pom.xml` nor `build.gradle*` present
- [x] Handles both Maven and Gradle inputs, each producing the same field shape (note: `pom.xml` parsed via regex, not a real XML parser — mirrors the codebase's existing pragmatic-regex style used for Gemfile/go.mod rather than pulling in `xml.etree`, sufficient for group-id/version-property extraction)
- [x] Wired into `detect()`'s ecosystem list; Maven preferred over Gradle when both present (mirrors `detect_python`'s pyproject-over-requirements preference)

**Verification:**
- [x] Tests pass: `/usr/bin/env python3 -m pytest tests/test_discovery.py -v`

**Dependencies:** None

**Files likely touched:**
- `src/open_context/discovery.py`

**Estimated scope:** Small: 1 file

---

## Checkpoint: PR3 complete
- [x] `/usr/bin/env python3 -m pytest tests/ -v` passes (56/56, full suite; 17/17 in test_discovery.py)
- [x] All three new detectors follow the `{value, confidence, source}` per-field shape, never blended
- [ ] Review with human before starting PR4

---

## PR4 — Schema traceability + flow relaxation

### Task 10: Add mandatory `source:` validation for `rules[]` and `domains[].patterns[]`

**Description:** In `schema.py`'s `validate_context()`, extend the existing
`rules[]` loop (currently checks `id`/`description` only, ~line 74-78) to
also require `source` (non-empty string). Add a new check for
`domains[i].patterns[]` — currently unvalidated entirely — requiring each
pattern entry to carry `source` too. Follow the existing error-string
convention (`f"rules[{i}] ({r.get('id', '?')}): missing 'source'"`).

**Acceptance criteria:**
- [x] `validate_context()` returns an error for any `rules[]` entry missing `source`
- [x] `validate_context()` returns an error for any `domains[].patterns[]` entry missing `source` — also extended to `domains[].subtypes[].patterns[]`, since that's where the real pattern content in both existing examples actually lives (`domains[].patterns[]` alone is unused by either example)
- [x] Error messages follow existing style (include index + name/id for identifiability)
- [x] Existing passing contexts with `source` present validate clean

**Verification:**
- [x] Tests pass: `/usr/bin/env python3 -m pytest tests/ -v`
- [x] Manual check: `tests/test_schema.py` added (9 tests) — covers missing/present `source` on rules, domain-level patterns, and subtype-level patterns

**Dependencies:** None within PR4 (can run before/parallel to Task 11)

**Files likely touched:**
- `src/open_context/schema.py`
- test coverage (check whether `schema.py` has dedicated tests or is only covered via `test_hook_integration.py`/`test_discovery.py` fixtures — add `tests/test_schema.py` if no dedicated file exists)

**Estimated scope:** Small: 1-2 files

---

### Task 11: Make `architecture.flow` optional in schema + patch resolver's hard dependency

**Description:** Two coupled changes, must land together:
1. `schema.py:47` — relax `elif not isinstance(arch.get("flow"), list) or not arch["flow"]:` so a missing/empty `flow` is valid (only reject if `flow` is present but not a list).
2. `resolver.py:474` — `base_flow: list[str] = list(context["architecture"]["flow"])` will `KeyError`/raise on a missing `flow` today. Patch to `list(context.get("architecture", {}).get("flow", []))` or equivalent, and verify downstream logic (lines ~479-534, which appends `extra_components` and builds `"components": base_flow`) degrades sensibly to an empty/component-less chain rather than erroring.

**Acceptance criteria:**
- [x] `validate_context()` accepts a context.yaml with `architecture: {}` or `architecture.flow: []` or `flow` key absent (or `architecture` key absent entirely)
- [x] `resolve()` runs without raising on a context.yaml with no `architecture.flow`, producing a sensible (possibly empty) `components` list
- [x] Existing contexts with `architecture.flow` populated behave identically to before (no regression)

**Verification:**
- [x] Tests pass: `/usr/bin/env python3 -m pytest tests/ -v`
- [x] Manual check: ran `resolve()` against a context.yaml with `architecture: {}` — no crash, `[COMPONENTS]` section renders empty

**Dependencies:** None within PR4, but logically must land before Task 13 (new example needs this to validate)

**Files likely touched:**
- `src/open_context/schema.py`
- `src/open_context/resolver.py`

**Estimated scope:** Small: 2 files

---

### Task 12: Backfill `source:` on the two existing examples

**Description:** Add `source:` to every `rules[]` and `domains[].patterns[]`
entry in `examples/rails-hmvc-sample/context.yaml` and
`examples/nextjs-sample/context.yaml`, using each example's own
`context-decisions.md` (Justification Changelog section) as the source of
truth for which file each pattern/rule was actually derived from — don't
guess; cross-check every entry against its documented evidence.

**Acceptance criteria:**
- [x] Every `rules[]` entry in both examples has a `source:` field (all `context-decisions.md`, since that's the governance doc covering the whole rule set in both examples)
- [x] Every pattern entry (subtype-level, where the real content lives) in both examples has a `source:` field
- [x] Each `source:` value is traceable to that example's `context-decisions.md` evidence — nextjs-sample's `owner_only_plan_change` cites the more specific external Next.js docs mentioned in its changelog entry, not just the umbrella file

**Verification:**
- [x] Tests pass: `open-context validate --context examples/rails-hmvc-sample/context.yaml --tests examples/rails-hmvc-sample/tests/` (17/17) and nextjs-sample (28/30, pre-existing unrelated amplification warning) — both 0 schema errors
- [x] Manual check: `validate_context()` run directly on both files, 0 errors each

**Dependencies:** Task 10 (schema must require the field before backfilling makes sense to verify against)

**Files likely touched:**
- `examples/rails-hmvc-sample/context.yaml`
- `examples/nextjs-sample/context.yaml`

**Estimated scope:** Medium: 2 files (but many entries each)

---

### Task 13: Add a new no-layer example

**Description:** New `examples/` directory for a repo type with no clear
layered architecture (e.g. a script/tooling monorepo or a data-pipeline
repo) — demonstrates `architecture.flow` legitimately absent, domains/rules
still populated with `source:` citations from that example's own
docs/AGENTS.md. Include a `context.yaml`, a minimal `context-decisions.md`
matching the established per-example convention, and a `tests/` phrasing
dir so `open-context validate` can run against it like the other examples.

**Acceptance criteria:**
- [x] New `examples/data-pipeline-sample/context.yaml` has no `architecture`/`flow` key at all (L2 section omitted entirely, not just emptied) and validates clean under Task 11's relaxed schema
- [x] 2 domains (`data_ingestion`, `report_generation`), each with 1 pattern + `rules[]` carrying real `source:` citations — citations point at real files added alongside the example (`AGENTS.md`, `docs/rules/ingestion-checklist.md`), not fabricated paths
- [x] `context-decisions.md` present, following the existing two examples' structure, plus a "Why architecture.flow is absent" section specific to the no-layer case

**Verification:**
- [x] Tests pass: `open-context validate --context examples/data-pipeline-sample/context.yaml --tests examples/data-pipeline-sample/tests/ --repo examples/data-pipeline-sample --strict` — 8/8 phrasings pass, 0 missing paths, exit 0 (one pre-existing-style amplification WARNING on `report`, same as nextjs-sample's `project` warning, not fixed there either — left as-is rather than distorting keyword design to silence a low-severity warning)

**Dependencies:** Task 11 (schema relaxation must exist first, or this example can't validate)

**Files likely touched:**
- `examples/data-pipeline-sample/context.yaml` (new)
- `examples/data-pipeline-sample/context-decisions.md` (new)
- `examples/data-pipeline-sample/tests/` (new)
- `examples/data-pipeline-sample/AGENTS.md`, `docs/rules/ingestion-checklist.md`, `scripts/ingest/pull_orders.py`, `scripts/reports/revenue_report.py` (new — real files the `source:`/`related_components` citations point at)

**Estimated scope:** Medium: 3+ files

---

## Checkpoint: PR4 complete
- [x] `/usr/bin/env python3 -m pytest tests/ -v` passes (65/65)
- [x] Both existing examples still validate after `source:` backfill
- [x] New no-layer example validates with absent `architecture.flow`
- [ ] Review with human before starting PR5

---

## PR5 — Wizard flow rewrite

### Task 14: Rewrite `/oc-setup` Phase 0/1 into docs-first single-confirm flow

**Description:** Rewrite `.claude/skills/oc-setup/SKILL.md`. Keep Q1
(scope) and Q2 (communication language) as separate questions, unchanged.
Replace Q3 (language/framework multiple-choice), Q4 (architecture pattern
multiple-choice — currently gated on the now-deleted 4b), and Q5 (actor
roles) with a single step: run `discover-docs` (PR2) to get
`docs_found`; if non-empty, read those files and synthesize a full draft
`context.yaml` (stack + architecture + actors) with `source:` citations
per rule/pattern pointing at the doc(s) read; if empty, fall back to
reading source code directly (still LLM-driven, no 4b), citing the actual
code file(s) read as `source:` instead. Present the full draft to the user
with a single Yes/Edit/Regenerate gate (same interaction shape as today's
Q4 gate, just covering the whole draft instead of only architecture).
Update Phase 3 (write context.yaml) to match — remove the old
CLAUDE.md/AGENTS.md → docs/ → README → OpenAPI → source scan-order
description since that's now formalized as the docs-first + fallback logic
above, not an ad-hoc scan order.

**Acceptance criteria:**
- [x] Q1 and Q2 text unchanged from current SKILL.md
- [x] Q3/Q4/Q5 replaced by one documented step (Question 3) that calls `discover-docs`, synthesizes a draft, and gates on Yes/Edit/Regenerate
- [x] SKILL.md explicitly documents the no-docs fallback (read source code, cite code file as `source:`)
- [x] Every generated rule/pattern in the documented flow is required to carry `source:`
- [x] Phase 5 validate loop (Iteration 1-3) description unchanged — out of scope for this task

**Verification:**
- [ ] Manual check: dry-run `/oc-setup` on a real repo with docs and one without — **NOT YET DONE**, this is an interactive skill (multi-turn Q&A), not a pytest-covered code path; left for the plan's separate "final verification" checkpoint below, which needs the user's actual involvement in the wizard's questions rather than self-simulated answers

**Dependencies:** Task 5 (`discover-docs` CLI must exist), Task 10 (schema must enforce `source:`), Task 11 (flow must be optional for repos without one)

**Files likely touched:**
- `.claude/skills/oc-setup/SKILL.md`

**Estimated scope:** Medium: 1 file, large rewrite

---

### Task 15: Rewrite `/oc-init` to use the same docs-first logic

**Description:** Update `.claude/skills/oc-init/SKILL.md` to call the same
`discover-docs` + synthesize-with-`source:` + code-fallback logic as Task
14, minus the interactive Yes/Edit/Regenerate gate (oc-init is
non-interactive by design — it regenerates from existing settings without
a wizard). Keep oc-init's existing "reads oc-settings.yaml if present"
behavior unchanged; only the doc/code-reading and `source:` citation logic
changes.

**Acceptance criteria:**
- [x] SKILL.md documents the same docs-first + fallback logic as Task 14, cross-referenced (points back to `/oc-setup`'s file for the full rationale) rather than duplicated
- [x] No new interactive wizard questions introduced (oc-init stays non-interactive)
- [x] Generated rules/patterns carry `source:` same as oc-setup's output

**Verification:**
- [ ] Manual check: dry-run `/oc-init` — same status as Task 14's verification, deferred to the final verification checkpoint

**Dependencies:** Task 14 (defines the shared docs-first logic this task reuses)

**Files likely touched:**
- `.claude/skills/oc-init/SKILL.md`

**Estimated scope:** Small: 1 file

---

### Task 16: Update CLAUDE.md to reflect the new architecture

**Description:** Update CLAUDE.md's "Phase 4 — Automated Discovery",
"Skills" table, "context.yaml Four-Layer Model", and "Known Discrepancy"
sections to describe: `docs_discovery.py` (Việc 1, deterministic) as a new
phase alongside 4a; the docs-first + code-fallback synthesis as what
`/oc-setup`/`/oc-init` now do instead of the old scan-order description;
the `source:` field as a schema requirement on L3 patterns/L4 rules; 4a's
expanded ecosystem list (Go/Rust/Java); and removal of 4b/HMVC (cross-check
against Task 3's PR1 sweep — this task is the final consistency pass after
all 4 other PRs, not a duplicate of Task 3).

**Acceptance criteria:**
- [x] CLAUDE.md accurately describes the codebase as it exists after PR1-PR5, with no stale references
- [x] New `docs_discovery.py` module documented in the "Repository Layout" / "Source Layout" tables
- [x] `source:` field documented as part of the Four-Layer Model description
- [x] Also swept `docs/reference.md`, `README.md`, `README.vi.md` — found and fixed stale Ruby/Node/Python-only and "up to 6/7 questions" claims left over from before PR3/PR5 landed (not caught by PR1's earlier sweep since those PRs didn't exist yet)

**Verification:**
- [x] Manual check: read CLAUDE.md top to bottom against the actual final codebase; `grep` swept for "up to 6/7 question", "Rails-only architecture", "architecture-chain auto-discovery" across CLAUDE.md/README*.md/docs//.claude/skills/ — 0 matches

**Dependencies:** Task 14, Task 15 (must describe the final wizard flow accurately)

**Files likely touched:**
- `CLAUDE.md`

**Estimated scope:** Small: 1 file

---

## Checkpoint: PR5 complete / final verification

All 5 PRs' code/schema/skill-doc changes are committed (65/65 pytest passing throughout). Live interactive dry run completed on 2026-08-27:

- [x] Ran `/oc-setup` on this repo itself (real docs: `CLAUDE.md`/`README.md`/`docs/reference.md`) — generated `.open-context/context.yaml` (4 domains, 4 rules), every `source:` cites `CLAUDE.md`, which was actually read. `architecture:` correctly omitted (no single layered chain — 3 hook entry points + CLI sharing a core module set). Caught and self-corrected one real content bug mid-run (`rule-04` missing `domain: [cli]`, was leaking into unrelated task resolutions) via Phase 5's iteration loop.
- [x] Ran `/oc-setup` on a fresh scratch repo (`no-docs-sample`, Flask task API, zero README/CLAUDE/AGENTS/docs) — `discover-docs` confirmed `docs_found: []`, triggering the no-docs fallback: read `app.py`/`routes/`/`services/`/`models/` directly, correctly inferred a real `route → service → model` chain from actual import call-evidence, and surfaced a genuine finding from a code comment (`services/task_service.py`'s "No ownership check here on purpose" became `rule-02`). Every `source:` cites a code file, not a doc.
- [x] `open-context validate --strict` passes on both: 17/17 phrasings (this repo), 8/8 phrasings (scratch repo), 0 schema errors, all declared `related_components` paths found on disk in both cases
- [x] All acceptance criteria across PR1-PR5 met
- [ ] Release process (per CLAUDE.md) followed: CHANGELOG.md entry, version bump, tag, GitHub release — not started; this dry run wrote `.open-context/` into this repo's own working tree (gitignored, not committed) purely for verification, separate from the release decision

`examples/data-pipeline-sample/` remains the committed, permanent reference example for the no-layer/docs-first case; the two dry runs above were ephemeral verification (this repo's `.open-context/` is gitignored, the scratch repo lives outside this repo entirely under the session scratchpad).
