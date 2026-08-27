# Reference

Deeper technical detail that doesn't need to be read before installing. See the [README](../README.md) for the pitch, demo, and install steps.

---

## Automated discovery

`/oc-setup` doesn't start blind. Before asking anything, it runs a deterministic stack detector and pre-fills the relevant questions — you still confirm every answer; nothing is written to `context.yaml` without an explicit yes.

**Stack detection** — Ruby (`Gemfile`), Node (`package.json`), Python (`pyproject.toml`/`requirements.txt`) only, this round. Reads structured config first; falls back to `CLAUDE.md`/`README.md` prose only for fields a manifest can't answer (e.g. a database's server version), at visibly lower confidence. Near-certain fields are shown as one batch-confirm line — press Enter to accept, or correct just the field that's wrong:

```
Detected: Ruby 3.2.1 · Rails 7.0.4.2 · Bundler · PostgreSQL · ActiveRecord · RSpec
Press Enter to use this, or type corrections.
```

Runs standalone too:

```bash
open-context detect --repo .
```

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

Working example with all coverage levels: [`examples/rails-hmvc-sample/`](../examples/rails-hmvc-sample/).

> [!IMPORTANT]
> A stale `context.yaml` produces no error — it routes silently to the wrong files. Version it alongside the code it describes. Treat `/oc-validate` failures as CI failures.

---

## Benchmarks

All benchmark numbers referenced in [`open-context-v0-architecture.md`](open-context-v0-architecture.md) (context reduction, architecture compliance, implementation quality) were measured against a **hand-written** Context Model. `/oc-setup`'s generated output passes automated routing validation, but its domain/pattern/constraint *content* has not been separately benchmarked against hand-written equivalents — especially for security-sensitive scoping rules. Review generated files before relying on them in production.

---

## Limitations

**Keyword ceiling.** Tasks phrased with synonyms or colloquial language may score below threshold and inject nothing. Run `/oc-validate` regularly to catch phrasing gaps.

---

## Known unmeasured

**Hook latency on non-SSD setups.** Fires on every prompt: filesystem traversal + resolver execution. Estimated < 5 ms on local SSD. On NFS mounts, Docker volumes, or WSL2 cross-filesystem paths (`/mnt/c/...`), latency is higher and has not been measured.

**Truncation at large scale.** Output cuts at the last section boundary before 9,500 characters. Synthetic benchmarks (15 domains, 12 rules, 3 simultaneous matches) produce ~9,700 characters — near the limit. At 20+ domains, truncation may become frequent. A compact output mode is the planned mitigation.

**Auto-generated `context.yaml` quality.** `/oc-setup` and `/oc-init` generate `context.yaml` via an LLM-driven wizard, validated automatically for routing correctness only. Whether generated patterns/constraints match the accuracy of hand-written equivalents — the property measured in `open-context-v0-architecture.md` — has not been tested.

**Discovery detector scope.** Stack detection covers Ruby/Node/Python only (verified against 4 real repos); other languages listed in early design notes (Go, Java, Rust) have no detector yet. Deliberately scoped to what has real ground truth to verify against, not the full original wishlist.
