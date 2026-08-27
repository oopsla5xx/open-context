---
name: oc-init
description: Scan the project and generate a context.yaml draft — reads oc-settings.yaml if present, otherwise infers everything from docs and source code. Runs validate automatically after generation.
---

Generate `.open-context/context.yaml` for this project by scanning existing documentation and source code.

## Step 1 — Load settings if available

Check for existing settings in this order:
1. `.open-context/oc-settings.yaml` in the current working directory
2. `$CLAUDE_PLUGIN_DATA/open-context/settings.json`

If found, use `language`, `framework`, `architecture`, and `actors` from settings as anchors for L1 and L2 — skip detecting those. If not found, infer everything from Phase 2.

## Step 2 — Discover project knowledge

Docs-first, same logic as `/oc-setup` (see that skill for the full rationale) — reused here, not reinvented, since both skills generate the same context.yaml shape from the same kind of evidence:

1. **List candidate docs (deterministic, no LLM).** Run:
   ```
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/src:${CLAUDE_PLUGIN_ROOT}/vendor" \
     python3 -m open_context.cli discover-docs --repo . --json
   ```
   This lists `README.md`/`CLAUDE.md`/`AGENTS.md` at any depth plus `docs/**/*.md` — a plain file listing, not a judgment call.
2. **Read what it found.** If `docs_found` is non-empty, Read every file it lists. Also check for OpenAPI/Swagger specs (`openapi.yaml`, `swagger.yaml`, `api/docs/`) — `discover-docs` doesn't list non-`.md` files, so look for these directly. Use this content for L1/L2 (when settings from Step 1 don't already cover it) and for L3/L4 domain and rule content.
3. **No docs found, or insufficient signal for a specific field** — fall back to reading source code directly the way a new engineer would: group request-entry files (controllers/handlers/routes, whatever the codebase's actual layout uses) by namespace into domain candidates, then confirm against the models/services beneath each. This replaces the old Rails-only "4b" detector for architecture inference — deliberate LLM judgment, not a fixed algorithm, so it works for any language/framework.

**Every rule and pattern written in Step 3 must carry `source:`** citing the file it came from — a doc path, an OpenAPI spec path, or a code file path for the fallback case. Not optional: `schema.py` rejects a `rules[]` or `patterns[]` entry with no `source:`.

## Step 3 — Generate context.yaml

**Overwrite guard:** if `.open-context/context.yaml` already exists, ask before writing:
> `.open-context/context.yaml` already exists. Overwrite? [y/N]

Default (empty answer or `N`) → stop here, do not write anything, leave the existing file untouched. Only proceed to write if the user answers `y`.

Before writing, ensure the repo-root `.gitignore` contains a `.open-context/` entry (create the file if missing, append the entry if no line already covers it, don't duplicate) — everything under `.open-context/` is local-only per developer, not shared with the team via git.

Write `.open-context/context.yaml` following this four-layer schema:

```yaml
# ── L1 STACK ──────────────────────────────────────────────────────────────────
project:
  name: <string>
  language: <string>
  language_version: "<detected-or-omit>"
  framework: <string>
  framework_version: "<detected-or-omit>"
  api_mode: <bool>
  api_versioning: <string>
  default_actor: <string>

# ── L2 ARCHITECTURE (omit this whole section if no clear layered architecture
#    was found — schema.py treats it as optional) ──────────────────────────────
architecture:
  name: <string>
  flow: [<component>, ...]

components:
  <component_name>:
    responsibility:
      - <string>
    allowed_dependencies:
      - <component_name>
    forbidden_dependencies:
      - <component_name>
    patterns:
      - id: <slug>
        description: <string>

actors:
  <actor_name>:
    description: <string>
    auth_method: <detected-or-omit>
    context_keys: [<detected-or-omit>]

# ── L3 DOMAINS ────────────────────────────────────────────────────────────────
domains:
  - name: <snake_case>
    coverage_level: routing_only | file_indexed | pattern_indexed
    keywords: [<string>, ...]
    typical_actors: [<actor_name>, ...]
    related_components:
      - <file_or_directory_path>
    subtypes:
      - name: <snake_case>
        keywords: [<string>, ...]
        related_components:
          - <path>
        patterns:
          - id: <slug>
            description: <string>
            source: <doc-or-code-file-this-was-read-from>   # required — see Step 2
    patterns:
      - id: <slug>
        description: <string>
        source: <doc-or-code-file-this-was-read-from>       # required — see Step 2

# ── L4 INVARIANTS ─────────────────────────────────────────────────────────────
rules:
  - id: rule-<NN>-<slug>
    description: <string>
    applies_to: [<component_name>, ...]
    domain: [<domain_name>]
    severity: critical | warning | info
    source: <doc-or-code-file-this-was-read-from>           # required — see Step 2
    guidance: |
      <concrete fix or code example>
```

**Coverage level guide:**
- `routing_only` — standard CRUD, files predictable from naming convention
- `file_indexed` — non-obvious paths, shared infra, concurrency
- `pattern_indexed` — subtle invariants needing explicit pattern guidance

**Keyword quality:** 5–12 per domain, include synonyms, avoid generic stop words (create/update/get are filtered).

## Step 4 — Generate test phrasing files

Create `tests/` next to `.open-context/context.yaml`. One `.txt` file per domain (`<domain_name>.txt`), 8–12 phrasings per file, one per line.

## Step 5 — Validate

Run:
```
python3 "${CLAUDE_PLUGIN_ROOT}/src/open_context/cli.py" validate \
  --context .open-context/context.yaml \
  --tests .open-context/tests/
```

Report coverage per domain. Flag any domain below 70% — suggest running `/oc-validate` after adjusting keywords or phrasings.

## Final report

After generation:
1. List domains identified and the primary signal source (which doc file or which code directory).
2. Note any domains where the signal was weak or the boundary was ambiguous.
3. Note any architecture rules found explicitly in docs vs. inferred from code patterns.
4. Tell the user that `context.yaml` and `tests/` live under `.open-context/`, which is gitignored — local to this machine, not shared with the team via git.
