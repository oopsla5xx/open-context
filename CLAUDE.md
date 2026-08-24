# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests (hook integration + discovery unit tests)
/usr/bin/env python3 -m pytest tests/ -v

# Run a single test
/usr/bin/env python3 -m pytest tests/test_hook_integration.py::test_json_nesting_correct -v

# Debug UserPromptSubmit hook manually (simulates what Claude Code fires)
echo '{"prompt":"renew book loan","cwd":"/path/to/project","user_prompt":"renew book loan"}' \
  | CLAUDE_PLUGIN_ROOT="$(pwd)" python3 scripts/resolve_hook.py

# Debug SessionStart hook manually
echo '{"cwd":"/path/to/project","hook_event_name":"SessionStart","session_id":"test"}' \
  | CLAUDE_PLUGIN_ROOT="$(pwd)" python3 scripts/session_hook.py

# Debug PreToolUse domain-drift hook manually (simulates an Edit/Write tool call)
echo '{"tool_name":"Edit","tool_input":{"file_path":"/path/to/project/app/models/patron.rb"},"cwd":"/path/to/project","session_id":"test"}' \
  | CLAUDE_PLUGIN_ROOT="$(pwd)" python3 scripts/drift_hook.py

# CLI (after pip install -e ., or PYTHONPATH="src:vendor" python3 -m open_context.cli ...)
open-context resolve "renew book loan" --context examples/rails-hmvc-sample/context.yaml
open-context validate --context examples/rails-hmvc-sample/context.yaml --tests examples/rails-hmvc-sample/tests/
open-context architecture validate --repo /path/to/rails-project
open-context detect --repo /path/to/project                    # Phase 4a — stack detection (Ruby/Node/Python)
open-context architecture discover --repo /path/to/rails-project  # Phase 4b — component-chain discovery (Rails only)
# All CLI commands accept --json
```

> Use `/usr/bin/env python3` instead of bare `python3` for pytest — the `rtk` hook intercepts bare commands and may fail.

## Release process

1. Add a `## [X.Y.Z] — YYYY-MM-DD` entry to `CHANGELOG.md` (Added/Changed/Fixed sections as needed).
2. Bump `version` in `.claude-plugin/plugin.json` to `X.Y.Z`.
3. Commit both as `open-context(release): bump to vX.Y.Z`.
4. `git tag open-context--vX.Y.Z`, then push the commit and the tag.
5. `gh release create open-context--vX.Y.Z --title "..." --notes "..."`.

`.github/workflows/release-changelog-check.yml` fails the tag-push workflow run if `CHANGELOG.md`
wasn't touched since the previous `open-context--v*` tag — it flags a skipped step after the fact, it
does not block the push itself.

## Repository Layout

This repo is both the CLI package (`src/open_context/`) and the Claude Code plugin (`.claude-plugin/`, `hooks/`, `scripts/`, `.claude/skills/`).

| Path | Role |
|------|------|
| `src/open_context/` | Core engine — resolver, validator, CLI, schema |
| `scripts/resolve_hook.py` | UserPromptSubmit hook — reads prompt from stdin, injects context |
| `scripts/resolve_hook.sh` | Shell entrypoint for UserPromptSubmit hook |
| `scripts/session_hook.py` | SessionStart hook — detects first-run, injects wizard trigger |
| `scripts/session_hook.sh` | Shell entrypoint for SessionStart hook |
| `scripts/drift_hook.py` | PreToolUse (`Edit`\|`Write`) hook — detects domain drift mid-turn, injects that domain's rules/patterns |
| `scripts/drift_hook.sh` | Shell entrypoint for the drift hook |
| `hooks/hooks.json` | Registers all three hooks |
| `.claude/skills/` | Five skills: `/oc-setup`, `/oc-init`, `/oc-resolve`, `/oc-validate`, `/oc-validate-architecture` |
| `.claude-plugin/plugin.json` | Plugin manifest (version, hooks path, skills path) |
| `vendor/yaml/` | Vendored PyYAML 6.0.3 — pure Python only, MIT license in `vendor/PYYAML_LICENSE` |
| `tests/test_hook_integration.py` | Integration tests — run hooks as real subprocesses |
| `tests/test_discovery.py`, `tests/test_architecture_discovery.py` | Unit tests (direct import, not subprocess) for Phase 4a/4b discovery modules |
| `examples/rails-hmvc-sample/` | Working 3-domain reference: library management API |

## Plugin Architecture

Three hooks, five skills. `CLAUDE_PLUGIN_ROOT` (set by Claude Code) locates `src/` and `vendor/` at runtime — no `pip install` needed for the hook path.

### SessionStart hook (`session_hook.py`)

Fires at session start. Checks for settings in order:
1. `.open-context/oc-settings.yaml` in cwd
2. `$CLAUDE_PLUGIN_DATA/open-context/settings.json`
3. Any `context.yaml` on the discovery path

If none found → injects `additionalContext` instructing Claude to start `/oc-setup` automatically. If any found → silent no-op.

### UserPromptSubmit hook (`resolve_hook.py`)

Fires on every prompt:
1. Reads `prompt` + `cwd` from JSON stdin
2. Locates `context.yaml`: `OPEN_CONTEXT_FILE` env var → `.open-context/context.yaml` → `context.yaml` in cwd → traverse to git root
3. Checks `matched_domains` **before** calling `format_report()` — exits with empty stdout if score = 0
4. Truncates at last `\n[` boundary before 9,500 chars (all section headers start with `\n[`)
5. Emits `{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "..."}}`

All errors → stderr only. Empty stdout + exit 0 = deliberate silent no-op.

### PreToolUse domain-drift hook (`drift_hook.py`), matcher `Edit|Write`

`resolve_hook.py` only sees the task text once, at the start of a turn. If Claude edits a file belonging to a domain that text never matched, that domain's rules/patterns were never surfaced. This hook catches that mid-turn:

1. Fires only on `Edit`/`Write` (not `Read`/`Grep`/`Bash` — no other tool call carries a `file_path` worth trusting)
2. Resolves `tool_input.file_path` to a path relative to repo root (`hook_utils.repo_root_for_context`), then reverse-looks-up which domain(s) own it via `resolver.domains_by_path()` — **domain-level `related_components` only**, subtypes are skipped because they're disambiguated by task-text keyword scoring and there's no task text here, only a path
3. Checks a per-`session_id` state file (`hook_utils.session_state_path`, under `$CLAUDE_PLUGIN_DATA/open-context/session-state/`, tmp-dir fallback) for domains already surfaced this turn; `resolve_hook.py` **overwrites** (not merges into) this file with its own `matched_domains` on every new prompt, so drift tracking resets per turn
4. For domains not yet in that set: injects `resolver.format_drift_report()` — rules + patterns only, deliberately no ACTION/ACTOR/COMPONENTS section, since those require task text this hook doesn't have — then merges the newly-surfaced domains into the state file
5. Never blocks the tool call — inject-only. `additionalContext`, no `permissionDecision`

Gated by `domain_drift_detection` in `oc-settings.yaml`/`settings.json` (`hook_utils.drift_detection_enabled`), **default `true`**. This is currently solo-dogfooded (single user, unreleased) — revisit the default before this ships to other users via a real version bump, once real latency/behavior data exists. `PreToolUse` runs synchronously and blocks the Edit/Write until the hook process exits; Claude Code's docs don't publish a latency/timeout figure for this, so don't assume it's free.

### Skills (`.claude/skills/`)

| Skill | What it does |
|-------|--------------|
| `oc-setup` | Phase 0 runs `detect` (+ `architecture discover` if Ruby/Rails) to pre-fill answers with real evidence, never auto-written → wizard (up to 7 questions) → generates settings + `context.yaml` + test files → validate loop (patch → retest → ask, max 3 rounds) |
| `oc-init` | Reads existing settings, scans docs/code, generates `context.yaml` + tests, validates |
| `oc-resolve` | Debug routing for a given task — shows all domain scores including below-threshold |
| `oc-validate` | Phrasing coverage + amplification safety check |
| `oc-validate-architecture` | Static scan of 6 HMVC rules (R1–R6) via regex on Rails source |

## Source Layout (`src/open_context/`)

| File | Responsibility |
|------|---------------|
| `resolver.py` | Core routing: tokenize → score → filter → match subtypes → build component chain → infer files. Also `domains_by_path()` (path → domain reverse-lookup) and `format_drift_report()`, used by the drift hook, not the prompt-time flow |
| `validator.py` | Phrasing coverage validator (runs `resolve()` on `.txt` test files) + HMVC architecture rule checker |
| `cli.py` | Subcommands: `resolve`, `validate`, `architecture validate`, `detect`, `architecture discover`. Core functions return plain dicts; CLI formats and sets exit codes. |
| `schema.py` | Validates `context.yaml` structure before any resolution |
| `discovery.py` | Phase 4a — stack detection (Ruby/Node/Python), per-field confidence + source, never blended into one score |
| `architecture_discovery.py` | Phase 4b — Rails-only component-chain discovery via real call-evidence in `app/`, never a fixed archetype |

### Resolution Algorithm

1. **Tokenize** — lowercase, split on non-alphanumeric, remove stop words
2. **Score domains** — exact match, underscore-part of compound keyword, prefix either direction
3. **Filter** — threshold = `max(2, top_score × 0.66)`; domains below discarded
4. **Match subtypes** — same scoring within each surviving domain
5. **Build component chain** — `architecture.flow` + `extra_components` from matched domains
6. **Infer files** — priority: subtype `related_components` → domain paths → domain directories

Action inference maps the first verb → `create/update/destroy/index/show` via `ACTION_VERBS` in `resolver.py`.

### context.yaml Four-Layer Model

- **L1 STACK** — language, framework, API versioning, default actor
- **L2 ARCHITECTURE** — component chain (`architecture.flow`) + per-component responsibilities, actors
- **L3 DOMAINS** — `keywords`, `coverage_level`, `related_components`, `subtypes`, `patterns`, `extra_components`
- **L4 INVARIANTS** — rules with `severity` + `guidance`; `domain:` field to scope a rule to specific domains

Coverage levels: `routing_only` / `file_indexed` / `pattern_indexed`.
Amplification risk: flagged when one token matches ≥4 keywords in the same domain.

Canonical reference: `examples/rails-hmvc-sample/context.yaml`.

## Phase 4 — Automated Discovery

Two independent, deterministic detectors that feed `/oc-setup`'s wizard — neither ever writes `context.yaml` directly; that only happens after the wizard's explicit approval in Phase 3.

**4a — Stack detection (`discovery.py`)**: Ruby (Gemfile), Node (package.json), Python (pyproject.toml/requirements.txt) only — scope is bounded to what has real ground truth to verify against (`qlear-v2-admin`/`qlear-v2-bot`, `rush86999/atom`), not the full list in the original spec (Go/Java/etc. have no verified detector yet). Non-recursive — reads only the given `--repo` path, one ecosystem-manifest scan per call; a monorepo with multiple ecosystems (e.g. a Python `backend/` next to a Next.js `frontend-nextjs/`) needs one `detect` call per subdirectory. Every field carries its own `{value, confidence, source}` — deliberately not blended into one score, since a field from a structured manifest (near-certain) and one recovered from CLAUDE.md/README prose (much less certain) are not comparable.

**4b — Architecture discovery (`architecture_discovery.py`)**: Rails-family apps only this round (no verified ground truth for other frameworks yet). Scans `app/` for real component directories and regex-based call-evidence between them (AST-lite, no AST engine) — never assumes a fixed 5-step HMVC chain; a real repo can turn out to use `admin → operation → form → model` with no serializer. Symlinked directories (e.g. a `shared/` submodule) are still scanned for call-evidence but flagged `external` rather than silently treated as owned code. `suggested_flow` is a full topological order (every connected component included, even ones in a cycle) — not a single greedy walk, which was found to silently drop real fan-out during validation. Whether to *propose* the discovered chain to the user is a small set of discrete red flags (zero edges; a cycle covering ≥50% of connected components), not a blended confidence score against a threshold — every weighted-penalty formula tried during development scored the hand-verified-correct `qlear-v2-admin` case at ~69%, just under a 70% cutoff, because it conflated real structural richness (multiple legitimate entry points) with detection uncertainty.

`/oc-setup` Phase 0 runs both, then folds results into its wizard questions: Question 3 (stack) uses one batch-confirm line since near-certain fields don't warrant per-field friction; Question 4 (architecture) uses the heavier Yes/Review/Select-another/Custom gate, because that is the one answer that is both genuinely uncertain and expensive to get wrong. `oc-init` and `oc-setup` both got an overwrite guard (ask `[y/N]` before clobbering an existing settings file or `context.yaml`) as part of this work — an unrelated silent-data-loss bug found while auditing the write paths, not a Phase 4 feature.

## Local-only config (`.open-context/`)

Everything `/oc-setup`/`/oc-init` generate — `context.yaml`, `oc-settings.yaml`, `tests/` — lives under `.open-context/` in the target project and is gitignored (both skills add a `.open-context/` entry to the project's `.gitignore` before writing). This is a deliberate product pivot: routing config is **local to each developer's machine**, not shared with the team via git. Each teammate who wants routing runs `/oc-setup` themselves.

This is why the GitHub Actions CI feature (a wizard question + a Phase that generated `.github/workflows/open-context-validate.yml`) was removed entirely, not just made optional: GitHub only runs workflows that are committed, and a CI checkout only has what git tracked — a gitignored `context.yaml`/`tests/` means there is nothing for `open-context validate` to see in CI. The underlying CLI (`open-context validate --strict`, `open-context architecture validate`) still works standalone; a user who wants CI back can commit `.open-context/` themselves and wire the CLI into their own workflow, but the wizard no longer offers to generate one by default.

**No backward compatibility** with the pre-this-change location (`.claude/context.yaml`, `.claude/oc-settings.yaml`, used by every released version through v0.1.9): this was a clean cutover, not a migration. Anyone who already ran `/oc-setup` under the old layout will look like a first-run project again and need to run `/oc-setup` again under `.open-context/`.

## Known Discrepancy

`pyproject.toml` sets `requires-python = ">=3.11"` (CLI), but the hook shell scripts accept `>=3.9` (to maximise compatibility on servers). If you update the hook's minimum Python, update both the shell scripts and this note.
