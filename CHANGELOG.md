# Changelog

All notable changes to this project will be documented in this file.

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
