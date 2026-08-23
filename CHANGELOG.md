# Changelog

All notable changes to this project will be documented in this file.

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
