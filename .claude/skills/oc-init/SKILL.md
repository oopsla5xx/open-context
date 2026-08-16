---
name: oc-init
description: Scan the project and generate a context.yaml draft — reads oc-settings.yaml if present, otherwise infers everything from docs and source code. Runs validate automatically after generation.
---

Generate `.claude/context.yaml` for this project by scanning existing documentation and source code.

## Step 1 — Load settings if available

Check for existing settings in this order:
1. `.claude/oc-settings.yaml` in the current working directory
2. `$CLAUDE_PLUGIN_DATA/open-context/settings.json`

If found, use `language`, `framework`, `architecture`, and `actors` from settings as anchors for L1 and L2 — skip detecting those. If not found, infer everything from Phase 2.

## Step 2 — Discover project knowledge

Scan in priority order, stopping as soon as you have enough signal:

1. `CLAUDE.md` / `AGENTS.md` — architecture conventions, component responsibilities, coding rules
2. `docs/` — ADRs, architecture diagrams, markdown
3. `README.md` / `README.*.md`
4. OpenAPI / Swagger specs (`openapi.yaml`, `swagger.yaml`, `api/docs/`)
5. Source code (only if docs give insufficient signal):
   - `app/controllers/` (or equivalent) — group by namespace → domain candidates
   - `app/operations/` / `app/services/` / `app/use_cases/` — confirm domain boundaries
   - `app/models/` — primary models per domain
   - Routes file — confirm resource grouping

## Step 3 — Generate context.yaml

Write `.claude/context.yaml` following this four-layer schema:

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

# ── L2 ARCHITECTURE ───────────────────────────────────────────────────────────
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
    patterns:
      - id: <slug>
        description: <string>

# ── L4 INVARIANTS ─────────────────────────────────────────────────────────────
rules:
  - id: rule-<NN>-<slug>
    description: <string>
    applies_to: [<component_name>, ...]
    domain: [<domain_name>]
    severity: critical | warning | info
    guidance: |
      <concrete fix or code example>
```

**Coverage level guide:**
- `routing_only` — standard CRUD, files predictable from naming convention
- `file_indexed` — non-obvious paths, shared infra, concurrency
- `pattern_indexed` — subtle invariants needing explicit pattern guidance

**Keyword quality:** 5–12 per domain, include synonyms, avoid generic stop words (create/update/get are filtered).

## Step 4 — Generate test phrasing files

Create `tests/` next to `.claude/context.yaml`. One `.txt` file per domain (`<domain_name>.txt`), 8–12 phrasings per file, one per line.

## Step 5 — Validate

Run:
```
python3 "${CLAUDE_PLUGIN_ROOT}/src/open_context/cli.py" validate \
  --context .claude/context.yaml \
  --tests .claude/tests/
```

Report coverage per domain. Flag any domain below 70% — suggest running `/oc-validate` after adjusting keywords or phrasings.

## Final report

After generation:
1. List domains identified and the primary signal source (which doc file or which code directory).
2. Note any domains where the signal was weak or the boundary was ambiguous.
3. Note any architecture rules found explicitly in docs vs. inferred from code patterns.
4. Tell the user to commit `context.yaml` and `tests/` alongside the code they describe.
