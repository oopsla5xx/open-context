# Open:Context v0 — Architecture & Experimental Results

> Zero-LLM context resolver for Rails HMVC codebases.
> Routes a natural-language task description to the exact context layers
> an AI agent needs — without vector search, embeddings, or inference calls.

---

## 1. Problem

When an AI agent implements a feature in a large Rails codebase, its context
window fills with irrelevant content: documentation for other domains, unrelated
models, architectural rules that don't apply to the current task. This forces
either expensive long contexts or lossy summarisation.

**Open:Context solves this at routing time** — before the agent reads a single
file. Given a task like `"renew book loan"`, it returns only:

- The relevant domain(s) and actors
- The HMVC component chain to traverse
- The specific files to read
- The architecture rules that apply
- Non-obvious implementation patterns for that domain

Everything else is explicitly excluded.

---

## 2. Design Constraints

| Constraint | Reason |
|---|---|
| No LLM calls | Resolver must be deterministic and free to run |
| No vector index | No indexing step; works on any codebase immediately |
| No code parsing | Reads only the context.yaml metadata file |
| Keyword-based | Predictable, debuggable, greppable routing logic |
| Data-driven | Domain knowledge lives in context.yaml, not in resolver code |

The last constraint is the most important. The resolver contains **zero
domain-specific logic** — adding a new domain, changing a routing rule, or
fixing a keyword collision requires editing context.yaml only.

---

## 3. Four-Layer Context Model

context.yaml is structured in four layers, each with a knowledge budget:

```
L1  STACK        — language, framework version, API mode                 (1 block)
L2  ARCHITECTURE — HMVC component chain, file patterns, actor types      (≤5 types)
L3  DOMAINS      — keyword sets, related files, subtypes, patterns       (≤8 domains)
L4  INVARIANTS   — critical architecture rules with guidance             (≤8 rules)
```

**L1 — Stack** tells the agent which conventions apply (Rails 7, api_mode,
versionist routing). Without this, agents guess framework defaults.

**L2 — Architecture** defines the fixed HMVC flow (`controller → operation →
form → model → serializer`) and the naming conventions that derive file paths
from action + resource names. The agent never has to guess where a file lives.

**L3 — Domains** is the routing layer. Each domain has:
- `keywords` — matched against task tokens
- `typical_actors` — who performs this action (determines controller namespace)
- `coverage_level` — `routing_only` / `file_indexed` / `pattern_indexed`
- `related_components` — specific files and directories to surface
- `subtypes` — narrower routing within a domain (e.g. checkout vs renewal)
- `extra_components` — additional flow components appended when this domain is matched
- `patterns` — non-obvious implementation knowledge (not architecture rules)

**L4 — Invariants** are always-applicable rules that the agent must respect,
with `severity: critical` and optional `guidance` code blocks.

---

## 4. Resolution Algorithm

Given a task string, the resolver performs six steps in sequence:

### Step 1 — Tokenize + action inference

```
"checkout overdue loan"
  → tokens: ['checkout', 'overdue', 'loan']
  → action: create  (verb 'checkout' → create-family)
```

Tokens are lowercased, split on non-alphanumeric, and filtered through a
stop-word list. Action is inferred from the first recognized verb.

### Step 2 — Domain scoring

Each domain is scored by counting how many of its keywords match task tokens.
Matching is flexible: a token matches a keyword if it equals the keyword,
equals any underscore-part of a compound keyword, or is a prefix match.

```
borrowing_management  keywords: [borrow, checkout, return, renew, loan, ...]
  token 'checkout' → matches keyword 'checkout'          +1
  token 'loan'     → matches keyword 'loan'              +1
  token 'overdue'  → matches keyword 'overdue'           +1
  score = 3
```

### Step 3 — Threshold filtering

Only domains above the routing threshold are kept:

```
threshold = max(2, top_score × 0.66)
```

The minimum of 2 prevents actor-qualifier words (e.g. "for patron") from
pulling in unrelated domains. The 66% band allows legitimate co-routing when
a task genuinely spans two domains.

### Step 4 — Subtype matching

For each matched domain that defines subtypes, the same keyword scoring runs
against the subtype keyword lists. The highest-scoring subtype is selected and
its `related_components` replace the domain-level directory pointers.

```
borrowing_management subtypes:
  checkout_copy  keywords: [borrow, checkout, new_loan]  score=2  ← selected
  renewal_copy   keywords: [renew, renewal, extend]      score=0
```

### Step 5 — Component chain construction

The base flow comes from `architecture.flow`. Extra components are appended
from any matched domain's `extra_components` field:

```
base_flow = [controller, operation, form, model, serializer]
borrowing_management.extra_components = [record_lock]
result    = [controller, operation, form, model, serializer, record_lock]
```

The `record_lock` reason is read from `borrowing_management.extra_component_reasons`
in context.yaml — not hardcoded in the resolver.

### Step 6 — File inference, rule selection, pattern collection

- Files come from matched subtype's `related_components` first (specific),
  then domain-level specific files (shared infrastructure), then domain
  directories as fallback.
- Rules are filtered by domain: general rules always apply; domain-scoped
  rules apply only when the matching domain is present.
- Patterns are collected from matched domains and high-confidence subtypes.

---

## 5. Example Resolution

**Task:** `checkout overdue loan`

```
TOKENS : ['checkout', 'overdue', 'loan']
ACTION : create

MATCHED DOMAINS
  borrowing_management  score=3  keywords=[checkout, loan, overdue]  actors=[patron]

MATCHED SUBTYPES
  checkout_copy  parent=borrowing_management  score=2  keywords=[checkout, new_loan]

ACTORS  [patron]

COMPONENTS
  controller   — instantiates one operation, renders via helper
  operation    — step_* method structure, validate before mutate
  form         — ApplicationForm, no side-effects
  model        — AR persistence
  serializer   — JSON formatting in controller
  record_lock  — with_lock on Book record (rule-06, TOCTOU prevention)

DOMAIN PATTERNS
  atomic_copy_decrement: check copy_count > 0 INSIDE with_lock block;
    decrement and create Loan in single transaction

RULES  (6 applicable)
  rule-01 No business logic in controller          [CRITICAL]
  rule-02 One operation per action                 [CRITICAL]
  rule-03 Step method structure                    [CRITICAL]
  rule-04 Validate before mutate                   [CRITICAL]
  rule-05 Form validation only                     [CRITICAL]
  rule-06 Borrowing with_lock                      [CRITICAL]
    Book.find(book_id).with_lock do
      form.valid!
      book.decrement!(:copy_count)
      Loan.create!(patron: current_patron, book:, due_date:)
    end

FILES  (6 entries)
  app/controllers/v1/patrons/checkouts_controller.rb   [subtype: checkout_copy]
  app/operations/v1/patrons/checkouts/create_operation.rb
  app/forms/v1/patrons/checkouts/create_form.rb
  app/controllers/v1/patrons/returns_controller.rb     [domain: borrowing]
  app/models/loan.rb
  app/models/book.rb

EXCLUDED
  Full architecture documentation, unrelated domain rules,
  database schema, routing table, source of uninvolved domains
```

---

## 6. Coverage Levels

| Level | When to use | What the agent gets |
|---|---|---|
| `routing_only` | Standard CRUD — naming convention is sufficient | Domain, actors, component chain, rules |
| `file_indexed` | Non-obvious paths, shared infrastructure, concurrency | + Specific files and directories |
| `pattern_indexed` | Subtle invariants that can't be inferred from file names | + Domain patterns with implementation guidance |

**Decision rule:** start at `routing_only`. Promote to `file_indexed` only
when the agent demonstrably reaches wrong files without explicit pointers.
Promote to `pattern_indexed` only when there is evidence (≥2 sessions) that
the pattern was missed without explicit inclusion.

---

## 7. Architecture Validator

The package includes a static analyser that checks 6 HMVC compliance rules
across the controller and operation layers:

| Rule | Scope | What it catches |
|---|---|---|
| R1 | controllers | AR queries or `raise` in action methods |
| R2 | operations | `Form.new()` without calling `.valid!` |
| R3 | operations | `Form.new(params)` instead of `permit_params` |
| R4 | controllers | `render json:` instead of `render_json()` |
| R5 | operations | Unscoped `ClassName.find(params[:id])` on tenant-scoped resources |
| R6 | operations | Bare `raise "..."` or standard Ruby exception classes |

The validator runs as `open-context architecture validate [--repo PATH] [--path DIR]`.
Exit code 1 if any violations found.

**R5 design note:** The validator distinguishes global models (shared
infrastructure that does not belong to a single tenant) from tenant-scoped
resources. Global models are excluded from the R5 check via a configurable
allowlist in `validator.py`. Extend the list only when a model is confirmed to
be genuinely tenant-independent.

In practice, running the validator against a production codebase discovered
unscoped resource lookups that manual review had missed across multiple
development iterations — the primary value of the rule engine.

---

## 8. Experimental Results

Measured across 10 implementation sessions on a production Rails API codebase
(~2,000 files, 8 business domains). Sessions used the same tasks in two
conditions: full AGENTS.md context vs. Open:Context resolved context.

| Hypothesis | Verdict | Evidence |
|---|---|---|
| H1: Context reduction ≥60% fewer tokens | ✅ CONFIRMED | −79% measured (avg resolved context vs full AGENTS.md) |
| H2: Architecture compliance preserved | ✅ CONFIRMED | 0 HMVC violations in resolved sessions; 2 in baseline |
| H3: Implementation quality equal or better | ✅ CONFIRMED | Resolved sessions produced correct step_* structure; baseline sessions guessed wrong actor namespace in 2/5 tasks |
| H4: Cross-domain tasks correctly co-routed | ✅ CONFIRMED | Tasks spanning 2 domains routed to both (threshold=0.66 × top_score) |
| H5: No false negatives on critical rules | ✅ CONFIRMED | rule-06 (concurrency) surfaced in every relevant session; 0 missed |

**On token reduction:** the −79% figure reflects the difference between
loading the full project context document (~3,000 tokens) versus the resolved
output for a specific task (~630 tokens average). The reduction varies by task:
routing_only domains produce smaller outputs; file_indexed + pattern_indexed
domains produce larger ones.

**On architecture validation:** the static rule engine found violations in
production code that had not been caught by manual review or existing tests.
R5 (unscoped resource lookup) is the highest-signal rule: it finds security-
relevant patterns that are invisible without systematic scanning.

---

## 9. Limitations

**Keyword-based routing has ceiling.** Tasks using synonyms or highly
colloquial language may not reach the routing threshold (score < 2) and fall
back to the generic HMVC path. Mitigation: maintain phrasing test files and
run `open-context validate` after any context.yaml change.

**context.yaml requires maintenance.** As the codebase evolves, domain
keywords and file lists go stale. A stale context.yaml produces no errors —
it silently routes to wrong files. Mitigation: version context.yaml with
the codebase; treat `open-context validate` failures as CI failures.

**Architecture rules are fixed.** The 6 HMVC rules in the validator reflect
one project's conventions. Projects with different naming, different exception
hierarchies, or different rendering patterns will need to adjust R1's allowed-
class list and R6's exception-class check.

**No runtime verification.** The resolver outputs a recommendation, not a
guarantee. It does not read the actual files — it infers them from metadata.
If context.yaml lists a file that no longer exists, the resolver outputs it
without error.

---

## 10. File Structure

```
src/open_context/
  __init__.py        — public API
  resolver.py        — resolution logic (tokenize, score, match, format)
  validator.py       — architecture rules (R1–R6) + phrasing coverage
  cli.py             — CLI entry point (resolve / validate / architecture validate)
  schema.py          — context.yaml schema validation

examples/rails-hmvc-sample/
  context.yaml           — working example: library management API (3 domains)
  context-decisions.md   — budget decisions and justification log
  tests/
    catalog_management.txt
    borrowing_management.txt
    member_management.txt

docs/
  open-context-v0-architecture.md   — this file
```

---

## 11. Quick Start

```bash
# resolve a task against your project's context
open-context resolve "implement member checkout" --context path/to/context.yaml

# run phrasing coverage check
open-context validate --context path/to/context.yaml

# run architecture compliance scan
open-context architecture validate --repo path/to/rails-project

# narrow scan to a subdirectory
open-context architecture validate --repo path/to/rails-project --path app/operations/v1/bookings
```

For context.yaml authoring guidance, see `examples/rails-hmvc-sample/context.yaml`
and `examples/rails-hmvc-sample/context-decisions.md`.
