# Changelog

All notable changes to this project will be documented in this file.

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
