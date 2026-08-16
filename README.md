<p align="center">
  <img src="assets/icon.webp" alt="Open:Context" width="48" style="vertical-align:middle;border-radius:12px">
</p>

<p align="center">
  <strong>Open:Context</strong>
</p>

<p align="center">
  Zero-LLM context routing for AI agents — hooks into every prompt,<br>
  injects only the relevant domain, files, and architecture rules.
</p>

<p align="center">
  <a href="https://github.com/oopsla5xx/open-context/releases"><img alt="Release" src="https://img.shields.io/github/v/release/oopsla5xx/open-context?style=flat-square&label=release&color=2ea44f"></a>
  <a href="./LICENSE"><img alt="License: Apache 2.0" src="https://img.shields.io/badge/license-Apache%202.0-blue?style=flat-square"></a>
  <img alt="Python 3.9+" src="https://img.shields.io/badge/python-3.9+-blue?style=flat-square&logo=python&logoColor=white">
  <img alt="Claude Code" src="https://img.shields.io/badge/Claude_Code-plugin-D97757?style=flat-square&logo=anthropic&logoColor=white">
</p>

<p align="center">
  <a href="./README.vi.md">Tiếng Việt</a> · <strong>English</strong>
</p>

---

AI agents on large codebases default to loading everything — full `CLAUDE.md`, docs for every domain, models that don't apply. The context window fills; precision drops. The fix isn't a smarter agent. It's a better signal going in.

Open:Context is a Claude Code plugin that fires a `UserPromptSubmit` hook on every prompt. It tokenizes the task, scores it against your `context.yaml`, and injects only the matching domain: component chain, relevant files, and applicable architecture rules. If nothing matches, it exits silently. Fully deterministic — no LLM in the routing path.

---

## What it looks like

You type a task. Before Claude responds, the hook has already resolved and injected:

```
[you type]  implement password reset for patron

[injected]  ────────────────────────────────────────────────────────────
            TASK   : implement password reset for patron
            ACTION : create
            ────────────────────────────────────────────────────────────

            [MATCHED DOMAINS]
              member_management   score=2  keywords=['patron']

            [COMPONENTS]
              ▸ CONTROLLER  — instantiates one Operation, renders via Serializer
              ▸ OPERATION   — step_* structure, Form.valid! before any write
              ▸ FORM        — ApplicationForm, validate only, no side-effects
              ▸ MODEL       — AR persistence
              ▸ SERIALIZER  — JSON in Controller, never in Operation

            [RULES]  (4 applicable)
              [CRITICAL] rule-01-no-business-logic-in-controller
              [CRITICAL] rule-02-one-operation-per-action
              [CRITICAL] rule-03-step-method-structure
              [CRITICAL] rule-04-validate-before-mutate

            [FILES]  (3 entries)
              app/controllers/v1/librarians/members_controller.rb
              app/operations/v1/librarians/members/create_operation.rb
              app/models/member.rb
```

Task matches no domain (e.g. "explain this error") → hook exits silently, nothing injected.

---

## Install

```bash
/plugin marketplace add oopsla5xx/open-context
/plugin install open-context@open-context
```

First time you open a project after install, the plugin detects that no configuration exists and starts the setup wizard automatically — asks 6 questions (scope, communication language, programming language, framework, architecture pattern, actor roles), then generates `context.yaml`, test phrasing files, and validates everything in one agentic loop. Nothing to run manually.

**Uninstall:**

```bash
/plugin uninstall open-context@open-context
/plugin marketplace remove open-context
```

**Reinstall from scratch:**

```bash
/plugin marketplace add oopsla5xx/open-context
/plugin install open-context@open-context
```

**Update to latest version:**

```bash
/plugin update open-context@open-context
```

> [!IMPORTANT]
> All benchmark numbers referenced in `docs/open-context-v0-architecture.md` (context reduction, architecture compliance, implementation quality) were measured against a **hand-written** Context Model. `/oc-setup`'s generated output passes automated routing validation, but its domain/pattern/constraint *content* has not been separately benchmarked against hand-written equivalents — especially for security-sensitive scoping rules. Review generated files before relying on them in production.

**CI or other agents (optional):**

```bash
pip install git+https://github.com/oopsla5xx/open-context.git
open-context validate --context path/to/context.yaml --tests path/to/tests/
```

---

## How it works

**First run — setup once per project:**

```mermaid
flowchart LR
    A[Install plugin] --> B[Open project\nSessionStart hook]
    B --> C{Config\nexists?}
    C -->|No| D["/oc-setup wizard\n5 questions"]
    D --> E[Generate\ncontext.yaml + tests]
    E --> F[Validate loop\nmax 3 rounds]
    F --> G["✓ Ready"]
    C -->|Yes| G
```

**Every prompt — automatic routing:**

```mermaid
flowchart LR
    A[User types task] --> B[UserPromptSubmit\nhook]
    B --> C[Tokenize\nScore domains]
    C -->|match| D["Inject\ndomains · files · rules"]
    C -->|no match| E[Silent exit]
    D --> F[Claude responds]
    E --> F
```

`context.yaml` is generated by `/oc-setup` or `/oc-init`. You can also write it by hand — see `examples/rails-hmvc-sample/` for a working 3-domain reference. PyYAML is vendored — no `pip install` needed for the hook.

---

## Skills

| Skill | What it does |
|-------|--------------|
| `/oc-setup` | Setup wizard: 5 questions → generates `context.yaml` + test files → validates *routing* in an agentic loop (patch → retest → ask → repeat up to 3 rounds). Routing validation confirms phrasings route correctly — it does not verify that generated patterns/constraints are accurate or complete. Review the output before relying on it for production work. Re-run any time to reconfigure. |
| `/oc-init` | Regenerate `context.yaml` for the current project — reads existing settings, scans docs and source code, validates automatically |
| `/oc-resolve <task>` | Debug routing — full resolver output including domains that scored below threshold |
| `/oc-validate` | Phrasing coverage tests + amplification safety check across `context.yaml` |
| `/oc-validate-architecture` | Static scan of 6 HMVC compliance rules (R1–R6) across the Rails codebase |

---

## context.yaml

Four layers, one file per project:

```
L1  STACK        — language, framework, API mode
L2  ARCHITECTURE — component chain and per-component responsibilities
L3  DOMAINS      — keywords, related files, subtypes, patterns per domain
L4  INVARIANTS   — always-applicable architecture rules with severity and guidance
```

Each domain declares a coverage level:

| Level | When |
|-------|------|
| `routing_only` | Standard CRUD — naming convention is enough |
| `file_indexed` | Non-obvious paths, shared infra, concurrency |
| `pattern_indexed` | Subtle invariants needing explicit guidance |

Working example with all coverage levels: [`examples/rails-hmvc-sample/`](examples/rails-hmvc-sample/).

> [!IMPORTANT]
> A stale `context.yaml` produces no error — it routes silently to the wrong files. Version it alongside the code it describes. Treat `/oc-validate` failures as CI failures.

---

## Architecture validator (R1–R6)

Static analysis for Rails HMVC codebases — six violation categories:

| Rule | Detects |
|------|---------|
| R1 | AR queries or `raise` inside controller action methods |
| R2 | `Form.new()` not followed by `.valid!` |
| R3 | `Form.new(params)` instead of `permit_params` |
| R4 | `render json:` instead of `render_json()` |
| R5 | Unscoped `Model.find(params[:id])` on tenant-scoped resources |
| R6 | Bare `raise "string"` instead of a custom exception class |

Runs grep across the real codebase — use for compliance audits, not routine checks.

---

## Limitations

**Keyword ceiling.** Tasks phrased with synonyms or colloquial language may score below threshold and inject nothing. Run `/oc-validate` regularly to catch phrasing gaps.

**No file existence check.** The resolver infers files from metadata — it does not verify that listed paths exist on disk.

**Architecture rules are fixed.** The 6 HMVC rules fit one project's conventions. Different naming or exception hierarchies require adjusting allowlists in `validator.py`.

---

## Known unmeasured

**Hook latency on non-SSD setups.** Fires on every prompt: filesystem traversal + resolver execution. Estimated < 5 ms on local SSD. On NFS mounts, Docker volumes, or WSL2 cross-filesystem paths (`/mnt/c/...`), latency is higher and has not been measured.

**Truncation at large scale.** Output cuts at the last section boundary before 9,500 characters. Synthetic benchmarks (15 domains, 12 rules, 3 simultaneous matches) produce ~9,700 characters — near the limit. At 20+ domains, truncation may become frequent. A compact output mode is the planned mitigation.

**Auto-generated `context.yaml` quality.** `/oc-setup` and `/oc-init` generate `context.yaml` via an LLM-driven wizard, validated automatically for routing correctness only. Whether generated patterns/constraints match the accuracy of hand-written equivalents — the property measured in `docs/open-context-v0-architecture.md` — has not been tested.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
PyYAML (vendored in `vendor/yaml/`) is MIT — see [`vendor/PYYAML_LICENSE`](vendor/PYYAML_LICENSE).
