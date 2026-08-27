# Reference

Deeper technical detail that doesn't need to be read before installing. See the [README](../README.md) for the pitch, demo, and install steps.

---

## Automated discovery

`/oc-setup` doesn't start blind. Before asking anything, it runs a deterministic stack detector and pre-fills the relevant questions — you still confirm every answer; nothing is written to `context.yaml` without an explicit yes.

**Stack detection** — Ruby (`Gemfile`), Node (`package.json`), Python (`pyproject.toml`/`requirements.txt`), Go (`go.mod`), Rust (`Cargo.toml`), Java (`pom.xml`/`build.gradle[.kts]`). Reads structured config first; falls back to `CLAUDE.md`/`README.md` prose only for fields a manifest can't answer (e.g. a database's server version), at visibly lower confidence. Near-certain fields are shown as one batch-confirm line — press Enter to accept, or correct just the field that's wrong:

```
Detected: Ruby 3.2.1 · Rails 7.0.4.2 · Bundler · PostgreSQL · ActiveRecord · RSpec
Press Enter to use this, or type corrections.
```

Runs standalone too:

```bash
open-context detect --repo .
```

**Project doc discovery** — a separate, deterministic file listing (no LLM): every `README.md`/`CLAUDE.md`/`AGENTS.md` at any depth, plus every `.md` file under any `docs/` directory. `/oc-setup`'s project-profile question reads whatever this finds to synthesize architecture and actors — with no docs, it falls back to reading source code directly, the way a new engineer would, rather than a fixed per-framework detector (there is no Rails-only "4b" equivalent for architecture anymore). Runs standalone too:

```bash
open-context discover-docs --repo .
```

---

## context.yaml

Four layers, one file per project — L2 is optional (a repo with no clear layered architecture omits it, routes purely on L3/L4):

```
L1  STACK        — language, framework, API mode
L2  ARCHITECTURE — (optional) component chain and per-component responsibilities
L3  DOMAINS      — keywords, related files, subtypes, patterns per domain
L4  INVARIANTS   — always-applicable architecture rules with severity and guidance
```

Every L3 pattern and L4 rule requires a `source:` field citing the doc or code file it was derived from — `schema.py` rejects one without it.

Each domain declares a coverage level:

| Level | When |
|-------|------|
| `routing_only` | Standard CRUD — naming convention is enough |
| `file_indexed` | Non-obvious paths, shared infra, concurrency |
| `pattern_indexed` | Subtle invariants needing explicit guidance |

Working example with all coverage levels: [`examples/rails-hmvc-sample/`](../examples/rails-hmvc-sample/). No-layer example (no `architecture.flow`): [`examples/data-pipeline-sample/`](../examples/data-pipeline-sample/).

> [!IMPORTANT]
> A stale `context.yaml` produces no error — it routes silently to the wrong files. Version it alongside the code it describes. Treat `/oc-validate` failures as CI failures.

---

## Benchmarks

All benchmark numbers referenced in [`open-context-v0-architecture.md`](open-context-v0-architecture.md) (context reduction, architecture compliance, implementation quality) were measured against a **hand-written** Context Model. `/oc-setup`'s generated output passes automated routing validation, but its domain/pattern/constraint *content* has not been separately benchmarked against hand-written equivalents — especially for security-sensitive scoping rules. Review generated files before relying on them in production.

---

## Limitations

**Keyword ceiling.** Tasks phrased with synonyms or colloquial language may score below threshold and inject nothing. Partially mitigated: a phrasing with exactly one keyword hit now still routes if that keyword belongs to only one domain (real, unambiguous evidence) — but a task using none of a domain's keywords at all, or only a keyword shared across domains, still scores too low. Run `/oc-validate` regularly to catch remaining phrasing gaps.

---

## Known unmeasured

**Hook latency on non-SSD setups.** Fires on every prompt: filesystem traversal + resolver execution. Estimated < 5 ms on local SSD. On NFS mounts, Docker volumes, or WSL2 cross-filesystem paths (`/mnt/c/...`), latency is higher and has not been measured.

**Truncation at large scale.** Output cuts at the last section boundary before 9,500 characters. Synthetic benchmarks (15 domains, 12 rules, 3 simultaneous matches) produce ~9,700 characters — near the limit. At 20+ domains, truncation may become frequent. A compact output mode is the planned mitigation.

**Auto-generated `context.yaml` quality.** `/oc-setup` and `/oc-init` generate `context.yaml` via an LLM-driven wizard, validated automatically for routing correctness only. Two live dry runs of the docs-first rewrite (one with real docs, one on a fresh no-docs repo exercising the code-reading fallback) confirmed the wizard produces a valid, correctly-routing `context.yaml` with accurate `source:` citations, and the fix loop caught and self-corrected one real content bug (a rule missing its `domain:` scope) mid-run. That's functional verification, not the comparative benchmark: whether generated patterns/constraints match the accuracy of hand-written equivalents — the property measured in `open-context-v0-architecture.md` — still has not been tested.

**Discovery detector scope.** Stack detection covers Ruby, Node, Python (verified against 4 real repos), plus Go/Rust/Java (added later). The Go/Rust/Java detectors are unit-tested against synthetic fixtures only, not a real checked-out repo the way the original three were — though CI's Python 3.9/3.10/3.11 matrix did catch one real bug (`detect_rust`'s `tomllib` fallback, stdlib only from 3.11) before it shipped, fixed in v0.3.1. Other ecosystems still have no detector.
