# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all integration tests
/usr/bin/env python3 -m pytest tests/test_hook_integration.py -v

# Run a single test
/usr/bin/env python3 -m pytest tests/test_hook_integration.py::test_json_nesting_correct -v

# Debug UserPromptSubmit hook manually (simulates what Claude Code fires)
echo '{"prompt":"renew book loan","cwd":"/path/to/project","user_prompt":"renew book loan"}' \
  | CLAUDE_PLUGIN_ROOT="$(pwd)" python3 scripts/resolve_hook.py

# Debug SessionStart hook manually
echo '{"cwd":"/path/to/project","hook_event_name":"SessionStart","session_id":"test"}' \
  | CLAUDE_PLUGIN_ROOT="$(pwd)" python3 scripts/session_hook.py

# CLI (after pip install -e .)
open-context resolve "renew book loan" --context examples/rails-hmvc-sample/context.yaml
open-context validate --context examples/rails-hmvc-sample/context.yaml --tests examples/rails-hmvc-sample/tests/
open-context architecture validate --repo /path/to/rails-project
# All CLI commands accept --json
```

> Use `/usr/bin/env python3` instead of bare `python3` for pytest — the `rtk` hook intercepts bare commands and may fail.

## Repository Layout

This repo is both the CLI package (`src/open_context/`) and the Claude Code plugin (`.claude-plugin/`, `hooks/`, `scripts/`, `.claude/skills/`).

| Path | Role |
|------|------|
| `src/open_context/` | Core engine — resolver, validator, CLI, schema |
| `scripts/resolve_hook.py` | UserPromptSubmit hook — reads prompt from stdin, injects context |
| `scripts/resolve_hook.sh` | Shell entrypoint for UserPromptSubmit hook |
| `scripts/session_hook.py` | SessionStart hook — detects first-run, injects wizard trigger |
| `scripts/session_hook.sh` | Shell entrypoint for SessionStart hook |
| `hooks/hooks.json` | Registers both hooks |
| `.claude/skills/` | Five skills: `/oc-setup`, `/oc-init`, `/oc-resolve`, `/oc-validate`, `/oc-validate-architecture` |
| `.claude-plugin/plugin.json` | Plugin manifest (version, hooks path, skills path) |
| `vendor/yaml/` | Vendored PyYAML 6.0.3 — pure Python only, MIT license in `vendor/PYYAML_LICENSE` |
| `tests/` | Integration tests — run hooks as real subprocesses |
| `examples/rails-hmvc-sample/` | Working 3-domain reference: library management API |

## Plugin Architecture

Two hooks, five skills. `CLAUDE_PLUGIN_ROOT` (set by Claude Code) locates `src/` and `vendor/` at runtime — no `pip install` needed for the hook path.

### SessionStart hook (`session_hook.py`)

Fires at session start. Checks for settings in order:
1. `.claude/oc-settings.yaml` in cwd
2. `$CLAUDE_PLUGIN_DATA/open-context/settings.json`
3. Any `context.yaml` on the discovery path

If none found → injects `additionalContext` instructing Claude to start `/oc-setup` automatically. If any found → silent no-op.

### UserPromptSubmit hook (`resolve_hook.py`)

Fires on every prompt:
1. Reads `prompt` + `cwd` from JSON stdin
2. Locates `context.yaml`: `OPEN_CONTEXT_FILE` env var → `.claude/context.yaml` → `context.yaml` in cwd → traverse to git root
3. Checks `matched_domains` **before** calling `format_report()` — exits with empty stdout if score = 0
4. Truncates at last `\n[` boundary before 9,500 chars (all section headers start with `\n[`)
5. Emits `{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "..."}}`

All errors → stderr only. Empty stdout + exit 0 = deliberate silent no-op.

### Skills (`.claude/skills/`)

| Skill | What it does |
|-------|--------------|
| `oc-setup` | Wizard (5 questions) → generates settings + `context.yaml` + test files → validate loop (patch → retest → ask, max 3 rounds) |
| `oc-init` | Reads existing settings, scans docs/code, generates `context.yaml` + tests, validates |
| `oc-resolve` | Debug routing for a given task — shows all domain scores including below-threshold |
| `oc-validate` | Phrasing coverage + amplification safety check |
| `oc-validate-architecture` | Static scan of 6 HMVC rules (R1–R6) via regex on Rails source |

## Source Layout (`src/open_context/`)

| File | Responsibility |
|------|---------------|
| `resolver.py` | Core routing: tokenize → score → filter → match subtypes → build component chain → infer files |
| `validator.py` | Phrasing coverage validator (runs `resolve()` on `.txt` test files) + HMVC architecture rule checker |
| `cli.py` | Three subcommands: `resolve`, `validate`, `architecture validate`. Core functions return plain dicts; CLI formats and sets exit codes. |
| `schema.py` | Validates `context.yaml` structure before any resolution |

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

## Known Discrepancy

`pyproject.toml` sets `requires-python = ">=3.11"` (CLI), but the hook shell scripts accept `>=3.9` (to maximise compatibility on servers). If you update the hook's minimum Python, update both the shell scripts and this note.
