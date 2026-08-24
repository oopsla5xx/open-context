---
name: oc-setup
description: First-run setup wizard for open-context — asks up to 6 questions about scope, communication language, programming language, framework, architecture, and actors — then generates context.yaml and test phrasing files under .open-context/ (gitignored, local to your machine) and validates in an agentic loop.
---

You are running the open-context first-run setup wizard. Execute all phases in order without waiting for the user to prompt you between phases. Be concise — summarise what you did after each phase in one line.

---

## Phase 0 — Discovery (silent, runs before any question)

Before asking anything, run automated detection so Question 3 and Question 4 can be pre-filled with real evidence instead of asked blind. Print nothing yet — results are folded into the relevant question below. If any step below fails or finds nothing, fall back silently to asking that question blind (no error, no partial pre-fill).

1. **Stack detection (4a).** Run:
   ```
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/src:${CLAUDE_PLUGIN_ROOT}/vendor" \
     python3 -m open_context.cli detect --repo . --json
   ```
   Keep the result for Question 3. If no ecosystem was detected (empty `ecosystems`), Question 3 is asked blind as written below.

   **If more than one ecosystem was detected** (e.g. a Rails app that also has a `package.json` for its JS asset pipeline, with no `framework` field found under Node — confirmed on qlear-v2-admin): prefer the ecosystem that has a detected `framework` value over one that doesn't — a repo's asset toolchain having a `package.json` doesn't make it "a Node project." If more than one ecosystem has a `framework` value, or none do, do not silently pick one — ask the user directly which ecosystem this question is about, listing what was found in each, before falling back to the blind flow below for that ecosystem.

2. **Architecture discovery (4b — Ruby/Rails only this round).** Only run this if step 1 found `"ecosystem": "ruby"` with `framework.value` == `"Rails"` (or `"Rails"`-family — case-insensitive). For any other language/framework, skip this step entirely — 4b does not support Next.js or other patterns yet, and guessing outside Rails is exactly the un-verified risk this phase avoids. If it applies, run:
   ```
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/src:${CLAUDE_PLUGIN_ROOT}/vendor" \
     python3 -m open_context.cli architecture discover --repo . --json
   ```
   Keep the result for Question 4. The result's `assess_confidence`-equivalent gate is printed in the human-readable (non-JSON) run as a `PROPOSE: yes/no` line with reasons — check that before deciding whether to pre-fill Question 4. If `PROPOSE: no`, Question 4 is asked blind as written below; do not show a rejected proposal to the user as if it were a real suggestion.

---

## Phase 1 — Wizard (up to 6 questions)

Ask each question one at a time. Present options as a numbered list. Wait for the user's answer before asking the next question.

open-context is local-only per developer: everything it generates (`.open-context/oc-settings.yaml`, `context.yaml`, `tests/`) lives under `.open-context/` and is gitignored (Phase 2 adds the entry) — it is not shared with the team via git. Each teammate who wants routing runs `/oc-setup` themselves.

**Question 1 — Scope**
> Where should open-context save its settings?
> 1. `project` — saved to `.open-context/oc-settings.yaml` in this repo (local to your machine, gitignored — applies only to this repo)
> 2. `global` — saved to `$CLAUDE_PLUGIN_DATA/open-context/settings.json` (your machine only, all projects)

**Question 2 — Communication language**
> What language should Claude use when talking about this project?
> 1. English
> 2. Vietnamese (Tiếng Việt)
> 3. Other (specify)

From this point on, use the chosen language for all responses in this session.

**Question 3 — Primary language & framework**

If Phase 0 step 1 detected an ecosystem, pre-fill with a single **batch-confirm** line — not the heavier 4-choice format used for Question 4. Stack fields (language/framework/version/db/orm/test framework) are near-certain when read from a structured manifest (Gemfile/package.json/pyproject.toml) — asking the user to click through a Yes/Review/Select-another/Custom gate for each of 5-6 fields that are almost always right trains a click-through reflex that then carries into Question 4, the one question that actually needs a real pause. Match friction to actual risk:

> Detected: `<language> <language_version>` · `<framework> <framework_version>` · `<package_manager>` · `<database>`[ + `<database_secondary>`] · `<orm>`[ + `<orm_secondary>`] · `<test_framework>`
> (source: Gemfile / package.json / pyproject.toml — see `--json` output for per-field confidence; omit any field absent from the detect result, don't print an empty placeholder for it)
> Press Enter to use this, or type corrections (e.g. "framework: Sinatra, test_framework: Minitest").

If the user just presses Enter (or says "yes"/"ok"/equivalent): use the detected values directly, do not ask the numbered lists below.
If the user types a correction: apply only the corrected field(s), keep the rest of the detected values.
If Phase 0 found nothing (no ecosystem detected) or detection is being overridden entirely, ask blind as before:

> What language does this project use?
> 1. Ruby
> 2. Python
> 3. TypeScript
> 4. JavaScript
> 5. Go
> 6. Java / Kotlin
> 7. Other (specify)

Then, based on the language chosen:
- Ruby → 1. Rails  2. Sinatra  3. Hanami  4. Other
- Python → 1. Django  2. FastAPI  3. Flask  4. Other
- TypeScript → 1. Next.js  2. NestJS  3. Express  4. Other
- JavaScript → 1. Next.js  2. Express  3. Nuxt  4. Other
- Go → 1. Gin  2. Echo  3. Fiber  4. Other
- Java/Kotlin → 1. Spring Boot  2. Ktor  3. Other
- Other language → ask free text

**Question 4 — Architecture pattern**

**This question never auto-writes anything — the detected chain below is a proposal, not a decision. `context.yaml` is only ever written in Phase 3, after this question resolves to an explicit Yes/Review→Yes/Select-another/Custom answer.**

If Phase 0 step 2 ran and printed `PROPOSE: yes`, pre-fill with the real discovered chain — never a fixed archetype name (that is exactly the guessing this phase exists to avoid; a real repo can turn out to use a different chain than any of the 5 standard options below, e.g. `admin → operation → form → model` with no serializer, ActiveAdmin as the entry point instead of a plain controller):

> Detected component chain (from real call-evidence in `app/`, not a template):
> `<suggested_flow joined by " → ">`
> Based on <N> discovered components, <M> call-evidence edges, no cycle detected.
> [if entry_candidates has more than 1] Note: multiple entry points found (`<entry_candidates>`) — the chain above is one linear reading of a graph that actually fans out; see Review for the full picture.
> [if external_components is non-empty] Note: `<external_components>` are defined in a shared/ submodule, not owned by this repo.
>
> 1. Yes — use this chain as-is
> 2. Review — see the full per-edge evidence (confidence + matched files) before deciding
> 3. Select another — pick from the standard patterns below
> 4. Custom — describe your own component chain

- If **Yes**: use `suggested_flow` as `architecture.flow`, and the discovered `allowed_dependencies` (from the `--json` output) as each component's `allowed_dependencies` in Phase 3 — this data already reflects real call-evidence (which component actually calls which), so do not ask the Phase 3 LLM step to re-derive it from scratch. `forbidden_dependencies` is not derived from discovery — leave that to Phase 3's judgment as before, since "what should be forbidden" is a design-intent call the detector deliberately does not make. Any component in `external_components` keeps its place in the flow but its `context.yaml` responsibilities entry MUST note it is external (not owned by this repo, e.g. a `shared/` submodule) — never presented the same as a component the repo actually owns.
- If **Review**: print the full edge table (`from -> to`, confidence %, `matched_files/total_files`, one or two example `file:line` hits per edge) plus `entry_candidates`, `terminal_candidates`, `unconnected`, `external_components` verbatim from the `--json` output. Then re-ask this same question (1/3/4 — Review is not a terminal answer, it feeds back into the choice with more information shown).
- If **Select another** or **Custom**: discard the detected proposal entirely and proceed exactly as the blind flow below.

If Phase 0 step 2 did not run (non-Rails, or no `app/` found) or printed `PROPOSE: no`, ask blind — do not show a rejected/skipped proposal as if it were a real suggestion, and do not guess at a confidence number to display:

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

**Overwrite guard:** if the target settings file (`.open-context/oc-settings.yaml` for scope `project`, or `$CLAUDE_PLUGIN_DATA/open-context/settings.json` for scope `global`) already exists, ask before writing:
> `<settings-path>` already exists. Overwrite? [y/N]

Default (empty answer or `N`) → stop the whole wizard here, do not write anything, leave the existing file untouched. Only proceed if the user answers `y`.

Write the settings file based on scope chosen in Question 1.

**If scope = `project`**, create `.open-context/oc-settings.yaml` in the current working directory:
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

**Ensure `.gitignore` (only when scope = `project`; a `global` scope writes nothing into the repo):** everything open-context generates lives under `.open-context/`, and it is local-only per developer, so run this whenever `.open-context/oc-settings.yaml` is about to be written (but not if the overwrite guard above stopped the wizard). Check the repo-root `.gitignore` (create it if missing) and, if no line already covers `.open-context/` (or `.open-context`), append one. Do not duplicate the entry if some form of it is already present.

---

## Phase 3 — Generate context.yaml

**Overwrite guard:** if `.open-context/context.yaml` already exists, ask before writing:
> `.open-context/context.yaml` already exists. Overwrite? [y/N]

Default (empty answer or `N`) → stop the whole wizard here, do not write anything, leave the existing file untouched. Only proceed if the user answers `y`.

Scan the project and generate `.open-context/context.yaml` using the wizard answers as L1 and L2 anchors.

**If Question 4 was answered "Yes" from a Phase 0 architecture proposal:** use its `allowed_dependencies` output directly for the corresponding components' `allowed_dependencies` field below — this is real call-evidence (component A's files actually reference component B), not a guess, so do not ask this Phase 3 step to re-derive it independently; a second, independently-guessed source for the same fact risks silently disagreeing with the first. `forbidden_dependencies` is unaffected — that is still this step's own judgment call in every case, detected or not.

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

### Output: `.open-context/context.yaml`

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

Create a `tests/` directory next to `.open-context/context.yaml` (i.e. `.open-context/tests/`). Write one `.txt` file per domain, named `<domain_name>.txt`. Each file contains 8–12 sample phrasings that should match that domain — one phrasing per line, no blank lines.

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
  --context .open-context/context.yaml \
  --tests .open-context/tests/
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

Settings   : <scope> → <path>
Context    : .open-context/context.yaml (<N> domains, <M> rules)
Tests      : .open-context/tests/ (<N> files, <M> phrasings)
Validate   : <pass/partial> — <X>/<N> domains above 70% coverage
.gitignore : <.open-context/ entry added> OR <already present> OR <skipped — global scope>

Next: run /oc-validate any time context.yaml changes.
Everything above lives under .open-context/ and is gitignored — local to this
machine, not shared with the team via git. If you want CI to validate
context.yaml on every PR, you'll need to commit .open-context/ yourself and
wire up `open-context validate --strict` / `open-context architecture
validate` in your own workflow — see the CLI usage in README.md.
```
