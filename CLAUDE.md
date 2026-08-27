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
open-context detect --repo /path/to/project                    # Phase 4a — stack detection (Ruby/Node/Python/Go/Rust/Java)
open-context discover-docs --repo /path/to/project              # Việc 1 — list README/CLAUDE/AGENTS.md + docs/**/*.md
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
| `.claude/skills/` | Four skills: `/oc-setup`, `/oc-init`, `/oc-resolve`, `/oc-validate` |
| `.claude-plugin/plugin.json` | Plugin manifest (version, hooks path, skills path) |
| `vendor/yaml/` | Vendored PyYAML 6.0.3 — pure Python only, MIT license in `vendor/PYYAML_LICENSE` |
| `tests/test_hook_integration.py` | Integration tests — run hooks as real subprocesses |
| `tests/test_discovery.py`, `tests/test_docs_discovery.py`, `tests/test_schema.py` | Unit tests (direct import, not subprocess) for `discovery.py`, `docs_discovery.py`, `schema.py` |
| `examples/rails-hmvc-sample/`, `examples/nextjs-sample/` | Working layered-architecture references (Rails HMVC, Next.js Server Actions) |
| `examples/data-pipeline-sample/` | Working no-layer reference — standalone scripts, no `architecture.flow` |

## Plugin Architecture

Three hooks, four skills. `CLAUDE_PLUGIN_ROOT` (set by Claude Code) locates `src/` and `vendor/` at runtime — no `pip install` needed for the hook path.

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
| `oc-setup` | Phase 0 runs `detect` + `discover-docs` to gather evidence, never auto-written → wizard (3 questions: scope, communication language, then one synthesized project-profile confirm built from docs — or source code as fallback — with a Yes/Edit/Regenerate gate) → generates settings + `context.yaml` + test files → validate loop (patch → retest → ask, max 3 rounds) |
| `oc-init` | Reads existing settings, then the same docs-first (+ code fallback) discovery as `/oc-setup`, generates `context.yaml` + tests, validates — non-interactive, no wizard |
| `oc-resolve` | Debug routing for a given task — shows all domain scores including below-threshold |
| `oc-validate` | Phrasing coverage + amplification safety check |

## Source Layout (`src/open_context/`)

| File | Responsibility |
|------|---------------|
| `resolver.py` | Core routing: tokenize → score → filter → match subtypes → build component chain → infer files. Also `domains_by_path()` (path → domain reverse-lookup) and `format_drift_report()`, used by the drift hook, not the prompt-time flow |
| `validator.py` | Phrasing coverage validator (runs `resolve()` on `.txt` test files) + amplification safety + file-existence checks |
| `cli.py` | Subcommands: `resolve`, `validate`, `detect`, `discover-docs`. Core functions return plain dicts; CLI formats and sets exit codes. |
| `schema.py` | Validates `context.yaml` structure before any resolution — requires `source:` on every `rules[]`/pattern entry, `architecture.flow` optional |
| `discovery.py` | Phase 4a — stack detection (Ruby/Node/Python/Go/Rust/Java), per-field confidence + source, never blended into one score |
| `docs_discovery.py` | Việc 1 — deterministic doc listing (`README.md`/`CLAUDE.md`/`AGENTS.md` at any depth, `docs/**/*.md`), no LLM, no scoring |

### Resolution Algorithm

1. **Tokenize** — lowercase, split on non-alphanumeric, remove stop words
2. **Score domains** — exact match, underscore-part of compound keyword, prefix either direction
3. **Filter** — threshold = `max(2, top_score × 0.66)`; domains below discarded. Exception: when nothing clears that floor at all (`top_score < 2`), a domain whose lone matched keyword no other domain shares routes anyway (`domain_unique_keywords()`) — fixes a confirmed real-world gap where a perfectly unambiguous single-keyword phrasing (e.g. "disconnect an integration") never routed (`docs/nextjs-real-world-test-report.md`, Finding A). Scoped narrowly to "nothing else would route anyway" — an incidental domain-unique word riding along in a sentence that already has a dominant match elsewhere does NOT also get injected.
4. **Match subtypes** — same scoring within each surviving domain
5. **Build component chain** — `architecture.flow` + `extra_components` from matched domains
6. **Infer files** — priority: subtype `related_components` → domain paths → domain directories

Action inference maps the first verb → `create/update/destroy/index/show` via `ACTION_VERBS` in `resolver.py`.

### context.yaml Four-Layer Model

- **L1 STACK** — language, framework, API versioning, default actor
- **L2 ARCHITECTURE** — *optional*: component chain (`architecture.flow`) + per-component responsibilities, actors. A repo with no clear layered architecture omits this section entirely; `resolver.py` degrades to an empty component chain rather than erroring
- **L3 DOMAINS** — `keywords`, `coverage_level`, `related_components`, `subtypes`, `patterns`, `extra_components`. Every pattern entry (domain- or subtype-level) requires `source:` — the file it was derived from
- **L4 INVARIANTS** — rules with `severity` + `guidance`; `domain:` field to scope a rule to specific domains. Every rule requires `source:`, same as L3 patterns

`source:` is a doc path (from `discover-docs`'s `docs_found`) when the docs-first path found the content, or a code file path when the no-docs fallback (direct code reading) produced it — traceability for what a generated rule/pattern was actually based on, not an unattributed LLM summary.

Coverage levels: `routing_only` / `file_indexed` / `pattern_indexed`.
Amplification risk: flagged when one token matches ≥4 keywords in the same domain.

Canonical references: `examples/rails-hmvc-sample/context.yaml` (layered architecture), `examples/data-pipeline-sample/context.yaml` (no `architecture.flow`).

## Phase 4 — Automated Discovery

**4a — Stack detection (`discovery.py`)**: Ruby (Gemfile), Node (package.json), Python (pyproject.toml/requirements.txt), Go (go.mod), Rust (Cargo.toml), Java (pom.xml/build.gradle[.kts]) — scope is bounded to what has real ground truth to verify against, not an open-ended list of every ecosystem. Non-recursive — reads only the given `--repo` path, one ecosystem-manifest scan per call; a monorepo with multiple ecosystems (e.g. a Python `backend/` next to a Next.js `frontend-nextjs/`) needs one `detect` call per subdirectory. Every field carries its own `{value, confidence, source}` — deliberately not blended into one score, since a field from a structured manifest (near-certain) and one recovered from CLAUDE.md/README prose (much less certain) are not comparable. Never writes `context.yaml` directly.

**Việc 1 — Project doc discovery (`docs_discovery.py`)**: a deterministic, LLM-free file listing — `README.md`/`CLAUDE.md`/`AGENTS.md` at any directory depth, plus every `.md` file under any `docs/` directory. Skips `node_modules`/`vendor`/`.git`/`dist`/`build`/`.open-context` by never descending into them. This is deliberately split from the LLM step that reads the files it finds (same 4a-code vs 4b-LLM split that shaped the original discovery design) — finding candidate files is pure code; deciding what they mean is the agentic wizard's job.

`/oc-setup` Phase 0 runs both, then Question 3 (the project-profile confirm — see that skill's file for the full flow) reads what `discover-docs` found and synthesizes stack/architecture/actors from it, citing `source:` per field. When no docs exist, it falls back to reading source code directly — this is what replaced the old Rails-only "4b" architecture-discovery detector, which was removed entirely rather than kept as a special case (see `tasks/plan.md` for the full rationale). `oc-init` and `oc-setup` both got an overwrite guard (ask `[y/N]` before clobbering an existing settings file or `context.yaml`) as part of earlier work — an unrelated silent-data-loss bug found while auditing the write paths, not a Phase 4 feature.

## Local-only config (`.open-context/`)

Everything `/oc-setup`/`/oc-init` generate — `context.yaml`, `oc-settings.yaml`, `tests/` — lives under `.open-context/` in the target project and is gitignored (both skills add a `.open-context/` entry to the project's `.gitignore` before writing). This is a deliberate product pivot: routing config is **local to each developer's machine**, not shared with the team via git. Each teammate who wants routing runs `/oc-setup` themselves.

This is why the GitHub Actions CI feature (a wizard question + a Phase that generated `.github/workflows/open-context-validate.yml`) was removed entirely, not just made optional: GitHub only runs workflows that are committed, and a CI checkout only has what git tracked — a gitignored `context.yaml`/`tests/` means there is nothing for `open-context validate` to see in CI. The underlying CLI (`open-context validate --strict`) still works standalone; a user who wants CI back can commit `.open-context/` themselves and wire the CLI into their own workflow, but the wizard no longer offers to generate one by default.

**No backward compatibility** with the pre-this-change location (`.claude/context.yaml`, `.claude/oc-settings.yaml`, used by every released version through v0.1.9): this was a clean cutover, not a migration. Anyone who already ran `/oc-setup` under the old layout will look like a first-run project again and need to run `/oc-setup` again under `.open-context/`.

## Known Discrepancy

`pyproject.toml` sets `requires-python = ">=3.11"` (CLI), but the hook shell scripts accept `>=3.9` (to maximise compatibility on servers). If you update the hook's minimum Python, update both the shell scripts and this note.
