# Changelog

All notable changes to this project will be documented in this file.

## [0.3.0] — 2026-08-27

Pivots from "Rails/HMVC-aware" to "any repo, any architecture" — a project's own docs (or its own code, with no docs) now drive setup instead of a fixed per-framework detector.

### Added

- `src/open_context/docs_discovery.py` — deterministic project-doc listing ("Việc 1"): `README.md`/`CLAUDE.md`/`AGENTS.md` at any directory depth plus every `.md` under any `docs/` directory, skipping `node_modules`/`vendor`/`.git`/`dist`/`build`/`.open-context`. No LLM, no scoring — pure glob, same code-vs-LLM split that shaped the original Phase 4a/4b design. New CLI subcommand `open-context discover-docs --repo <path> [--json]`.
- Phase 4a stack detection (`discovery.py`) extended to Go (`go.mod`), Rust (`Cargo.toml`), and Java (`pom.xml`/`build.gradle[.kts]`) — same `{value, confidence, source}` per-field shape as the existing Ruby/Node/Python detectors, Maven preferred over Gradle when both are present.
- `schema.py` now requires a `source:` field on every `rules[]` entry and every `patterns[]` entry (domain- or subtype-level) — traceability for what a generated rule/pattern was actually derived from (a doc path or, for the no-docs fallback, a code file path), not an unattributed LLM summary.
- `examples/data-pipeline-sample/` — new reference example with **no** `architecture.flow` at all (a standalone-scripts repo, no controller/model layering), demonstrating the no-layer case end to end: real `AGENTS.md`/`docs/rules/*.md`, `context.yaml` with accurate `source:` citations, passing `tests/`.
- `tests/test_docs_discovery.py`, `tests/test_schema.py` — new unit-test files (23 tests total) covering the new module and the schema's traceability/optional-flow rules.

### Changed

- `/oc-setup`'s wizard drops from up to 6 questions to 3: scope, communication language, and a single synthesized "project profile" (language/framework/architecture/actors) with one Yes/Edit/Regenerate confirm. The profile reads `discover-docs`'s output first — falling back to reading source code directly (the way a new engineer would) when a repo has no docs at all. This replaces the old separate language/framework question, the architecture-pattern question, and the actor-roles question.
- `/oc-init` gets the same docs-first + code-fallback discovery logic as `/oc-setup`, still fully non-interactive.
- `architecture.flow` (L2) is now optional in `schema.py` and `resolver.py` — a repo with no clear layered architecture can omit L2 entirely; the resolver degrades to an empty component chain instead of erroring. `examples/rails-hmvc-sample/` and `examples/nextjs-sample/` were backfilled with `source:` citations (from their existing `context-decisions.md` files) to satisfy the new schema requirement.
- `README.md`/`README.vi.md`: badges and example links updated for Go/Rust/Java auto-detect and the new `data-pipeline-sample`/`nextjs-sample` references.

### Removed (breaking)

- **`architecture_discovery.py` (Phase 4b, Rails-only component-chain discovery) is deleted, not deprecated.** It never generalized past Rails and is fully replaced by the docs-first + code-reading Question 3 above.
- **The 6-rule HMVC compliance validator is deleted** — `validator.py`'s `run_arch_validate`/R1–R6 checks, the `open-context architecture validate` and `open-context architecture discover` CLI subcommands, and the `/oc-validate-architecture` skill are all gone. This repo no longer ships any Rails-specific tooling.
- No migration path for either removal — a project relying on `architecture validate`/`architecture discover` needs to pin an earlier version or maintain that logic itself.

### Added

- `scripts/drift_hook.py` + `.sh` — new `PreToolUse` hook (matcher `Edit|Write`): when Claude edits a file belonging to a domain that the turn's original prompt never matched, injects that domain's rules/patterns before the write happens (`resolver.domains_by_path()`, `resolver.format_drift_report()`). Domain-level `related_components` only — subtypes need task-text keyword scoring, which a bare file path doesn't have.
- Per-`session_id` drift state (`hook_utils.session_state_path()` et al., under `$CLAUDE_PLUGIN_DATA/open-context/session-state/`, tmp-dir fallback): tracks which domains were already surfaced this turn so the same domain isn't re-injected on every subsequent edit; reset on every new `UserPromptSubmit`.
- `domain_drift_detection` setting (`oc-settings.yaml` project scope / `settings.json` global scope) to opt out — **defaults to `true`**. Measured cost: ~125–250ms per `Edit`/`Write` call (Python cold-start + pure-Python YAML parse per invocation, since each hook call is a fresh process) — kept on by default after review, but real-world reports of noticeable lag are the first thing to check if this needs revisiting.
- 15 new tests covering the drift hook and the `.open-context/` layout below.

### Changed

- **Everything `/oc-setup` and `/oc-init` generate — `context.yaml`, `oc-settings.yaml`, `tests/` — now lives under `.open-context/` and is gitignored automatically** (both skills add the entry to the project's `.gitignore` before writing). Routing config is local to each developer's machine, not shared with the team via git; each teammate who wants routing runs `/oc-setup` themselves.
- Removed the GitHub Actions CI generation feature entirely (the wizard's CI question and the phase that wrote `.github/workflows/open-context-validate.yml`) — incompatible with a gitignored `context.yaml`: GitHub only runs committed workflows, and a CI checkout only has what git tracked, so there was nothing for `open-context validate` to see by default. The CLI (`open-context validate --strict`, `open-context architecture validate`) still works standalone for anyone who commits `.open-context/` themselves and wires it into their own workflow.
- `README.md` / `README.vi.md`: single unified install path (`/plugin marketplace add` → `/plugin install` → `/oc-setup`); dropped the separate "use the CLI directly" instructions.

### Breaking

- **No backward compatibility** with the `.claude/context.yaml` / `.claude/oc-settings.yaml` location used by every release through v0.1.9. This was a clean cutover, not a migration — anyone who already ran `/oc-setup` will see their project as first-run again and needs to re-run `/oc-setup` under `.open-context/`.

## [0.1.9] — 2026-08-23

### Fixed

- `resolver.score_domain`: an underscore-joined compound keyword (e.g. `company_member`) scored only 1 point even when every one of its parts appeared as a task token — dedup was keyed by keyword name, not by which parts actually matched. Domains that happened to only have compound keywords lost routing to domains with several unrelated single-word keywords. Now scores one point per distinct matched part.
- `resolver.score_domain`: plural task tokens with an irregular ending (`companies`) never matched their singular keyword (`company`) — `"companies".startswith("company")` is `False`. Added a small `_singularize()` helper (`ies→y`, `es→''`, `s→''`) checked both directions.
- Fixing the compound-keyword scoring above surfaced a second, previously-masked bug: very short tokens (e.g. `me`) were prefix-matching unrelated longer keywords (`member`) and, once compound keywords scored correctly, could push an unrelated domain over threshold. Prefix matching now requires the token to be at least 3 characters.
- `schema.validate_context`: a keyword containing a literal space (e.g. `"system setting"`) is silently unmatchable as a two-word AND-condition — the resolver only ever splits on `_`, so a space-keyword degrades to a loose prefix check against the whole phrase. Now rejected at validation time with a suggested `_`-joined replacement.
- `cli._load_and_validate`: a syntax error in `context.yaml` (e.g. an unquoted `:` inside a scalar) raised an uncaught `yaml.YAMLError` and printed a raw Python traceback. Now caught and reported as `error: invalid YAML in <path>: line X, column Y: <reason>`.
- `validator.run_phrasing_tests`: a phrasing test file named after a *subtype* (e.g. `company_domains.txt`) was silently never loaded — coverage was computed only over top-level domain names. Subtype test files are now loaded and checked against `matched_subtypes`; `open-context validate` prints them in a separate `[SUBTYPE COVERAGE]` section when present.

## [0.1.8] — 2026-08-23

### Added

- `src/open_context/discovery.py` — Phase 4a stack detection: Ruby (`Gemfile`), Node (`package.json`), Python (`pyproject.toml`/`requirements.txt`); every field returns `{value, confidence, source}` rather than one blended score
- `src/open_context/architecture_discovery.py` — Phase 4b Rails-only component-chain discovery via real call-evidence in `app/`: topological `suggested_flow` (not a greedy walk, to avoid dropping real fan-out), explicit cycle detection, symlinked/submodule components flagged `external`
- New CLI subcommands: `open-context detect --repo <path>` and `open-context architecture discover --repo <path>` (both accept `--json`)
- `/oc-setup` Phase 0 — runs both detectors silently before the wizard, pre-filling Question 3 (stack) as one batch-confirm line and Question 4 (architecture) behind a Yes/Review/Select-another/Custom gate; nothing is written to `context.yaml` without explicit approval in Phase 3
- 19 new unit tests (`tests/test_discovery.py`, `tests/test_architecture_discovery.py`)

### Fixed

- `/oc-init` and `/oc-setup` now ask `[y/N]` before overwriting an existing `context.yaml` or settings file (previously silent data loss)

### Changed

- `.github/workflows/pylint.yml`: `actions/setup-python` v4 → v5; CI now runs the full test suite (`pytest tests/`) instead of only hook integration tests
- `README.md`, `README.vi.md`, `CLAUDE.md`: document the two new detectors and the "Automated discovery" flow

## [0.1.7] — 2026-08-18

### Changed

- `resolver.py`: `component_reason()` no longer hardcodes Rails component descriptions (`controller`/`operation`/`form`/`model`/`serializer`) — now derives text from `context.yaml`'s own `components.<name>.responsibility`/`patterns`, so a non-Rails component named `model` (or any of those 5 names) no longer leaks Rails-specific text (`ApplicationForm`, `attr_reader`)
- `resolver.py`: `.ts`/`.tsx` files are no longer misclassified as directories in file inference; the "specific file" check is now based on whether the path has any extension, not a hardcoded `.rb`/`.py`/`.js` allowlist
- `resolver.py`: the directory-search naming hint is now derived from `context.yaml`'s own `files.<component>.naming` templates instead of a hardcoded `.rb` hint
- `__init__.py`, `cli.py`: wording no longer describes the resolver itself as Rails-only (`architecture validate` remains genuinely Rails-only and its help text still says so)

### Added

- `examples/nextjs-sample/` — Next.js App Router / Server Actions reference sample, used to benchmark the resolver on a second framework
- `docs/nextjs-effectiveness-report.md`, `docs/nextjs-real-world-test-report.md` — benchmark results and findings from testing against a synthetic and a real-world Next.js codebase

## [0.1.0] — 2026-08-16

First public release.

### Added

- `UserPromptSubmit` hook — fires on every Claude Code prompt, resolves task against `context.yaml`, injects matched domain context (components, files, rules) or exits silently if no match
- `SessionStart` hook — detects first-run (no settings or context.yaml found), injects wizard trigger so Claude starts `/oc-setup` automatically
- Five skills: `/oc-setup`, `/oc-init`, `/oc-resolve`, `/oc-validate`, `/oc-validate-architecture`
- `/oc-setup` agentic wizard — 5 questions (scope, language, framework, architecture, actors) → generates `oc-settings.yaml` + `context.yaml` + test phrasing files → validate loop (patch → retest → ask user, max 3 rounds)
- `/oc-init` — scan project docs and source code, generate `context.yaml` using existing settings
- `/oc-resolve` — debug routing for any task, shows all domain scores including below-threshold
- `/oc-validate` — phrasing coverage tests + amplification safety check
- `/oc-validate-architecture` — static scan of 6 HMVC compliance rules (R1–R6) via regex on Rails source
- Four-layer `context.yaml` schema: L1 STACK, L2 ARCHITECTURE, L3 DOMAINS, L4 INVARIANTS
- Three coverage levels: `routing_only`, `file_indexed`, `pattern_indexed`
- PyYAML 6.0.3 vendored (pure Python, MIT) — no `pip install` required for the hook path
- Working example: `examples/rails-hmvc-sample/` — library management API with 3 domains
- CLI (`open-context resolve / validate / architecture validate`) for CI and non-Claude-Code use
- Integration test suite — 12 tests covering both hooks as real subprocesses
- CI: pylint (3 Python versions), pip-audit, pytest (3 Python versions)

### Known unmeasured

- Hook latency on NFS / Docker / WSL2 cross-filesystem setups
- Output truncation frequency at 20+ domains in production
