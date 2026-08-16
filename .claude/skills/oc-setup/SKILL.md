---
name: oc-setup
description: First-run setup wizard for open-context — asks 6 questions about scope, communication language, programming language, framework, architecture, and actors, then automatically generates context.yaml, test phrasing files, and validates in an agentic loop.
---

You are running the open-context first-run setup wizard. Execute all phases in order without waiting for the user to prompt you between phases. Be concise — summarise what you did after each phase in one line.

---

## Phase 1 — Wizard (6 questions)

Ask each question one at a time. Present options as a numbered list. Wait for the user's answer before asking the next question.

**Question 1 — Scope**
> Where should open-context save its settings?
> 1. `project` — saved to `.claude/oc-settings.yaml` in this repo (committed with the team)
> 2. `global` — saved to `$CLAUDE_PLUGIN_DATA/open-context/settings.json` (your machine only, all projects)

**Question 2 — Communication language**
> What language should Claude use when talking about this project?
> 1. English
> 2. Vietnamese (Tiếng Việt)
> 3. Other (specify)

From this point on, use the chosen language for all responses in this session.

**Question 3 — Primary language**
> What language does this project use?
> 1. Ruby
> 2. Python
> 3. TypeScript
> 4. JavaScript
> 5. Go
> 6. Java / Kotlin
> 7. Other (specify)

**Question 3 — Framework**
Present options based on the language chosen in Question 2:
- Ruby → 1. Rails  2. Sinatra  3. Hanami  4. Other
- Python → 1. Django  2. FastAPI  3. Flask  4. Other
- TypeScript → 1. Next.js  2. NestJS  3. Express  4. Other
- JavaScript → 1. Next.js  2. Express  3. Nuxt  4. Other
- Go → 1. Gin  2. Echo  3. Fiber  4. Other
- Java/Kotlin → 1. Spring Boot  2. Ktor  3. Other
- Other language → ask free text

**Question 4 — Architecture pattern**
> What architectural pattern does this project follow?
> 1. HMVC — controller → operation → form → model → serializer
> 2. Service Objects — controller → service → model
> 3. Clean / Hexagonal — use case → repository → entity
> 4. Standard MVC — controller → model → view
> 5. Other (describe the component chain briefly)

**Question 5 — Primary actor roles**
> Who are the primary actors in this system? Select all that apply (comma-separated numbers), or type custom roles:
> 1. admin
> 2. user
> 3. guest
> 4. tenant
> 5. staff
> 6. customer
> 7. Other (specify)

---

## Phase 2 — Save settings

Write the settings file based on scope chosen in Question 1.

**If scope = `project`**, create `.claude/oc-settings.yaml` in the current working directory:
```yaml
scope: project
communication_language: <answer-2>
language: <answer-3>
framework: <answer-4>
architecture:
  name: <answer-5-name>
  flow: [<component-chain-from-answer-5>]
actors: [<answer-6-list>]
```

**If scope = `global`**, create `$CLAUDE_PLUGIN_DATA/open-context/settings.json`:
```json
{
  "scope": "global",
  "communication_language": "<answer-2>",
  "language": "<answer-3>",
  "framework": "<answer-4>",
  "architecture": {
    "name": "<answer-5-name>",
    "flow": ["<component>", "..."]
  },
  "actors": ["<actor>", "..."]
}
```

Create parent directories if they don't exist.

---

## Phase 3 — Generate context.yaml

Scan the project and generate `.claude/context.yaml` using the wizard answers as L1 and L2 anchors.

### Discovery (scan in priority order)

1. `CLAUDE.md` / `AGENTS.md` — architecture conventions, rules, coding invariants
2. `docs/` — ADRs, architecture docs, markdown files
3. `README.md` / `README.*.md`
4. OpenAPI / Swagger specs (`openapi.yaml`, `swagger.yaml`, `api/docs/`)
5. Source code if docs give insufficient signal:
   - `app/controllers/` (or equivalent) — group by namespace → domain candidates
   - `app/operations/` / `app/services/` / `app/use_cases/` — confirm domain boundaries
   - `app/models/` — primary models per domain
   - Routes file — confirm resource grouping

### Output: `.claude/context.yaml`

Write the file following this exact four-layer schema:

```yaml
# ── L1 STACK ──────────────────────────────────────────────────────────────────
project:
  name: <string>
  language: <from-settings>
  language_version: "<detected-or-omit>"
  framework: <from-settings>
  framework_version: "<detected-or-omit>"
  api_mode: <bool>
  api_versioning: <string>        # versionist / path / header / none
  default_actor: <first-actor-from-settings>

# ── L2 ARCHITECTURE ───────────────────────────────────────────────────────────
architecture:
  name: <from-settings>
  flow: [<component-chain-from-settings>]

components:
  <component_name>:               # one block per component in architecture.flow
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
  <actor_name>:                   # one block per actor from settings
    description: <string>
    auth_method: <detected-or-omit>
    context_keys: [<detected-or-omit>]

# ── L3 DOMAINS ────────────────────────────────────────────────────────────────
domains:
  - name: <snake_case>
    coverage_level: routing_only | file_indexed | pattern_indexed
    keywords: [<string>, ...]     # 5–12 terms a developer would type
    typical_actors: [<actor_name>, ...]
    related_components:           # required for file_indexed and pattern_indexed
      - <file_or_directory_path>
    subtypes:
      - name: <snake_case>
        keywords: [<string>, ...]
        related_components:
          - <path>
        patterns:
          - id: <slug>
            description: <string>
    patterns:                     # for pattern_indexed only
      - id: <slug>
        description: <string>

# ── L4 INVARIANTS ─────────────────────────────────────────────────────────────
rules:
  - id: rule-<NN>-<slug>
    description: <string>
    applies_to: [<component_name>, ...]
    domain: [<domain_name>]       # omit if universal
    severity: critical | warning | info
    guidance: |
      <concrete code example or fix>
```

### Coverage level guide

| Signal | Level |
|--------|-------|
| Standard CRUD, files predictable from naming | `routing_only` |
| Non-obvious paths, shared infra, concurrency | `file_indexed` |
| Subtle invariants, locking, event emission | `pattern_indexed` |

### Keyword quality guide

- Include domain nouns AND verbs: `invoice`, `subscribe`, `authenticate`
- Include synonyms the team uses: `loan` AND `borrow`
- Avoid generic stop words: `create`, `update`, `get` (filtered by resolver)
- Target 5–12 per domain; >15 risks amplification warnings

---

## Phase 4 — Generate test phrasing files

Create a `tests/` directory next to `.claude/context.yaml`. Write one `.txt` file per domain, named `<domain_name>.txt`. Each file contains 8–12 sample phrasings that should match that domain — one phrasing per line, no blank lines.

Example for a `billing` domain (`billing.txt`):
```
create invoice for customer | billing
send payment reminder | billing
process subscription renewal | billing
handle failed charge | billing
issue refund for last payment | billing
update billing plan to enterprise | billing
list overdue invoices | billing
charge customer for upgrade | billing
```

Each line must be `phrasing | expected_domain` — the validator splits on `|` and checks that the resolver routes to that domain.

---

## Phase 5 — Validate and fix loop

Run the validation CLI and fix issues in up to 3 iterations.

**Run validation:**
```
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/src:${CLAUDE_PLUGIN_ROOT}/vendor" \
  python3 -m open_context.cli validate \
  --context .claude/context.yaml \
  --tests .claude/tests/
```

**If all domains pass:** report success and stop.

**If any domain fails**, enter the fix loop:

### Iteration 1 — Patch keywords
For each failing domain:
- Read the validate output to identify which phrasings didn't match
- Add the unmatched terms as keywords to that domain in `context.yaml`
- Do not rewrite the entire file — patch only the failing domains
- Re-run validation

### Iteration 2 — Supplement test phrasings
If domains still fail after keyword patching:
- Check if the test `.txt` files have sufficient variety
- Add 5 more phrasings per still-failing domain that reflect different ways to phrase the same task
- Re-run validation

### Iteration 3 — Ask the user
If domains still fail after 2 iterations:
- List each still-failing domain, its current coverage %, and the unmatched phrasings
- Ask: "Domain `<name>` is at <X>% coverage. What terms does your team use to refer to this domain?"
- Incorporate the user's answer and re-run validation one final time

**Exit condition:** stop after 3 iterations OR when no improvement between consecutive iterations. Report final coverage per domain and flag any domain still below 70% for human review.

---

## Final report

After all phases complete, print a summary:
```
open-context setup complete

Settings : <scope> → <path>
Context  : .claude/context.yaml (<N> domains, <M> rules)
Tests    : .claude/tests/ (<N> files)
Validate : <pass/partial> — <X>/<N> domains above 70% coverage

Next: run /oc-validate any time context.yaml changes.
Commit context.yaml and tests/ alongside the code they describe.
```
