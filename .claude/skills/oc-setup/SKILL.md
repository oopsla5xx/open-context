---
name: oc-setup
description: First-run setup wizard for open-context — asks 2 questions (scope, communication language), then reads the project's own docs (or source code, if none exist) to synthesize a project profile (stack, architecture, actors) for a single confirm — then generates context.yaml and test phrasing files under .open-context/ (gitignored, local to your machine) and validates in an agentic loop.
---

You are running the open-context first-run setup wizard. Execute all phases in order without waiting for the user to prompt you between phases. Be concise — summarise what you did after each phase in one line.

---

## Phase 0 — Discovery (silent, runs before any question)

Before asking anything, run automated detection so Question 3 can be pre-filled with real evidence instead of asked blind. Print nothing yet — results are folded into Question 3 below. If a step fails or finds nothing, fall back silently to the next step (no error, no partial pre-fill).

1. **Stack detection (4a).** Run:
   ```
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/src:${CLAUDE_PLUGIN_ROOT}/vendor" \
     python3 -m open_context.cli detect --repo . --json
   ```
   Keep the result for Question 3 as the near-certain source for language/framework/version/package-manager/database/orm/test-framework — these fields come from a structured manifest (Gemfile/package.json/pyproject.toml/go.mod/Cargo.toml/pom.xml/build.gradle), which outranks a docs-derived guess for the same field. If no ecosystem was detected (empty `ecosystems`), Question 3 falls through to docs/code for these fields too, same as everything else.

   **If more than one ecosystem was detected** (e.g. a Rails app that also has a `package.json` for its JS asset pipeline, with no `framework` field found under Node — confirmed on qlear-v2-admin): prefer the ecosystem that has a detected `framework` value over one that doesn't — a repo's asset toolchain having a `package.json` doesn't make it "a Node project." If more than one ecosystem has a `framework` value, or none do, do not silently pick one — ask the user directly which ecosystem this question is about, listing what was found in each.

2. **Project doc discovery (Việc 1).** Run:
   ```
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/src:${CLAUDE_PLUGIN_ROOT}/vendor" \
     python3 -m open_context.cli discover-docs --repo . --json
   ```
   This is a deterministic file listing only (README.md/CLAUDE.md/AGENTS.md at any depth, plus `docs/**/*.md`) — it does not read content or decide anything. Keep the `docs_found` list for Question 3, which does the actual reading.

Architecture discovery (formerly Phase 0 step "4b", Rails-only) has been removed — it never generalized past Rails. What replaces it is Question 3 below: read the docs this step found (or the source code directly, if none were found) the way an engineer new to the codebase would, rather than a fixed detector.

---

## Phase 1 — Wizard (3 questions)

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

**Question 3 — Project profile (language, framework, architecture, actors)**

**This question never auto-writes anything — `context.yaml` is only ever written in Phase 3, after this question resolves to an explicit Yes/Edit answer.**

One synthesized draft, not four separate questions — the whole point of this rewrite is that a repo's own docs (or, failing that, its own code) already say what its stack/architecture/actors are; the job here is to read and cite that, not to make the user re-type it through a multiple-choice menu. Determine each field in this priority order, tracking which source each field actually came from — do not blend a docs claim and a code-reading guess into one unattributed line:

1. **Stack fields (language/framework/version/db/orm/test framework)** — use Phase 0 step 1's `detect()` result when it found something; that's a structured-manifest read, near-certain, and outranks anything read from prose. Cite the manifest file (e.g. `Gemfile`, `go.mod`) as the source.
2. **Everything else (architecture/component chain, primary actor roles), and any stack field `detect()` didn't find** — if Phase 0 step 2's `docs_found` is non-empty, Read every file it listed. Synthesize architecture as a real component chain if the docs actually describe one (e.g. "controllers call operations, operations call models") — never force a fixed archetype name onto a repo that doesn't have one; if the docs (or the repo's actual shape) don't support a clean layered chain, say so plainly rather than guessing a plausible-sounding one. Cite the specific doc path read for each field.
3. **No docs found at all, or docs left a field unresolved** — read the source code directly the way a new engineer would: list the top-level directory structure, open a handful of representative files (entry points, routing/handler files, whatever the directory layout suggests is load-bearing), and infer from there. This replaces the old Rails-only "4b" detector — it is deliberately LLM judgment now, not a fixed algorithm, so it works for any language/framework. Cite the actual code file(s) read as the source, not a doc path.
4. **Still nothing usable** (e.g. a near-empty new repo with no docs and barely any code) — ask directly, as a last resort, not a default:
   > What language/framework does this project use, and what's the rough shape of its architecture (e.g. controller → service → model, or "no clear layers")? Who are the primary actors (e.g. admin, user, guest)?

Present the synthesized draft as one block, every field tagged with its source:

> Detected project profile:
> Language/Framework: `<language> <version>` · `<framework> <version>` (source: `<manifest file>`)
> Architecture: `<component chain>` OR `no clear layered architecture — will be omitted from context.yaml` (source: `<doc or code file>`)
> Actors: `<comma-separated list>` (source: `<doc or code file>`)
> [any field determined via step 4's blind fallback above: mark it "(no signal found — asked directly)" instead of a file source]
>
> 1. Yes — use this as-is
> 2. Edit — describe what's wrong, only that gets corrected
> 3. Regenerate — re-read with different guidance (e.g. "check `docs/architecture/` instead")

If **Edit**: apply only the corrected field(s), keep the rest of the draft.
If **Regenerate**: re-run the relevant discovery step with the user's guidance, then re-present the draft.

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
language: <from-confirmed-project-profile>
framework: <from-confirmed-project-profile>
architecture:
  name: <from-confirmed-project-profile, or omit entirely if no clear layered architecture>
  flow: [<component-chain, or omit if no clear layered architecture>]
actors: [<from-confirmed-project-profile>]
```

**If scope = `global`**, create `$CLAUDE_PLUGIN_DATA/open-context/settings.json`:
```json
{
  "scope": "global",
  "communication_language": "<answer-2>",
  "language": "<from-confirmed-project-profile>",
  "framework": "<from-confirmed-project-profile>",
  "architecture": {
    "name": "<from-confirmed-project-profile, or omit entirely if no clear layered architecture>",
    "flow": ["<component>", "..."]
  },
  "actors": ["<from-confirmed-project-profile>"]
}
```

Create parent directories if they don't exist.

**Ensure `.gitignore` (only when scope = `project`; a `global` scope writes nothing into the repo):** everything open-context generates lives under `.open-context/`, and it is local-only per developer, so run this whenever `.open-context/oc-settings.yaml` is about to be written (but not if the overwrite guard above stopped the wizard). Check the repo-root `.gitignore` (create it if missing) and, if no line already covers `.open-context/` (or `.open-context`), append one. Do not duplicate the entry if some form of it is already present.

---

## Phase 3 — Generate context.yaml

**Overwrite guard:** if `.open-context/context.yaml` already exists, ask before writing:
> `.open-context/context.yaml` already exists. Overwrite? [y/N]

Default (empty answer or `N`) → stop the whole wizard here, do not write anything, leave the existing file untouched. Only proceed if the user answers `y`.

Use the confirmed Question 3 project profile as the L1/L2 anchors — do not re-derive language/framework/architecture/actors independently here; that was already resolved (and its sources already cited) in Question 3.

### Discovery for L3 domains and L4 rules

The L2 profile answers "what shape is this codebase" — this step answers "what are its business domains and invariants," a separate question Question 3 doesn't cover. Reuse Phase 0 step 2's `docs_found` list — Read every file in it (skip ones already read for Question 3 only if nothing new would be learned; most docs mix architecture and domain/rule content, so re-reading is usually still worth it). Also check for OpenAPI/Swagger specs (`openapi.yaml`, `swagger.yaml`, `api/docs/`) — `discover-docs` doesn't list these (non-`.md`), so look for them directly.

If `docs_found` was empty, or the docs read gave insufficient signal for domain boundaries specifically: fall back to reading source code the way Question 3's fallback did — group request-entry files (controllers/handlers/routes, whatever the codebase's actual layout uses) by namespace into domain candidates, then confirm against the models/services beneath each.

**Every rule and pattern written below must carry `source:`** citing the file it came from — a doc path from `docs_found`, an OpenAPI spec path, or a code file path for the fallback case. This is not optional: `schema.py` rejects a `rules[]` or `patterns[]` entry with no `source:`.

### Output: `.open-context/context.yaml`

Write the file following this exact four-layer schema:

```yaml
# ── L1 STACK ──────────────────────────────────────────────────────────────────
project:
  name: <string>
  language: <from-confirmed-project-profile>
  language_version: "<detected-or-omit>"
  framework: <from-confirmed-project-profile>
  framework_version: "<detected-or-omit>"
  api_mode: <bool>
  api_versioning: <string>        # versionist / path / header / none
  default_actor: <first-actor-from-confirmed-project-profile>

# ── L2 ARCHITECTURE (omit this whole section if the confirmed profile found no
#    clear layered architecture — schema.py treats it as optional) ────────────
architecture:
  name: <from-confirmed-project-profile>
  flow: [<component-chain-from-confirmed-project-profile>]

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
  <actor_name>:                   # one block per actor from confirmed profile
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
            source: <doc-or-code-file-this-was-read-from>   # required — see note above
    patterns:                     # for pattern_indexed only
      - id: <slug>
        description: <string>
        source: <doc-or-code-file-this-was-read-from>       # required — see note above

# ── L4 INVARIANTS ─────────────────────────────────────────────────────────────
rules:
  - id: rule-<NN>-<slug>
    description: <string>
    applies_to: [<component_name>, ...]
    domain: [<domain_name>]       # omit if universal
    severity: critical | warning | info
    source: <doc-or-code-file-this-was-read-from>           # required — see note above
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
wire up `open-context validate --strict` in your own workflow — see the CLI
usage in README.md.
```
