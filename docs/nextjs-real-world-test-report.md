# Real-World Test — `open-context` against an unmodified Next.js codebase

## Why this exists

The earlier benchmark (`docs/nextjs-effectiveness-report.md`) had a real
methodological weakness: I
wrote the Next.js skeleton *and* its `context.yaml` at the same time, so paths
and keywords were always going to line up. That only proves the resolver can
route correctly on code shaped to fit it. This test instead points
`open-context` at a real, unmodified, third-party Next.js codebase — one where
the backend is a genuinely separate service, not Prisma embedded in the
Next.js app — to see whether the tool holds up on code nobody adapted for it.

**Not a formal spec'd phase** — this is exploratory dogfooding, reported
directly, with no separate planning artifact. Nothing from the target repo is kept: no
`context.yaml`, no example, no code. Only this report and any `open-context`
fixes are retained. The clone itself lives in a session scratchpad directory
and gets deleted after this report is written.

## Target

[`rush86999/atom`](https://github.com/rush86999/atom) ("ATOM Platform" — an
AGPL-licensed, open-source AI agent workforce app), shallow-cloned, scoped to
its `frontend-nextjs/` subdirectory treated as its own project root — per
explicit scope decision, the separate Python `backend/` (and mobile/desktop/
menubar variants) were out of scope; the backend is an external dependency
the frontend calls, not something `open-context` needs to model.

Confirmed facts about the target (not assumed):
- **Pages Router**, not App Router — Next.js 16.2.2, TypeScript.
- No `CLAUDE.md`/`AGENTS.md` in `frontend-nextjs/` — only a generic
  create-next-app `README.md` plus `docs/API_ROBUSTNESS.md` and
  `docs/FRONTEND_COVERAGE.md`.
- Backend reached via axios wrappers in `lib/` (`api.ts`, `boards-api.ts`,
  `hubspotApi.ts`, ...), default base URL `http://127.0.0.1:8000` — no
  Server Actions, no Prisma anywhere in the codebase.
- Real source (`pages/`, `components/`, `lib/`, `hooks/`) sits at the same
  top level as a large amount of unrelated cruft — old progress reports,
  one-off fix/analysis scripts, stray logs — a genuinely messy real
  repository, not a curated one.

## What I built

A `context.yaml` (7 domains: `finance`, `workflow_automation`,
`chat_assistant`, `third_party_integrations`, `boards_canvas`,
`agent_management`, `account_settings`) derived from actually reading the
real directory structure and a couple of real docs — not from any signal I
authored myself. Architecture modeled as `page → hook → api_client` (Pages
Router + axios), distinct from the Server-Actions-first model used in the
earlier synthetic sample. One real invariant captured directly from the
code: every vendor integration page needs a matching `pages/oauth/{vendor}/`
callback route, or the OAuth connect flow dead-ends (`third_party_integrations`
→ `oauth_callback_per_vendor` pattern, `rule-03-oauth-callback-required`).

## Result 1 — file existence: clean

`open-context validate --repo frontend-nextjs/`: **28/28 declared
`related_components` paths found**, 0 missing, against the real cloned
source tree. Directory-path inference from a one-pass read of the repo
structure was accurate.

## Result 2 — phrasing coverage: bad on the first pass, then good

This is the real finding of this test.

**Cold run** (context.yaml + 56 natural-language test phrasings, written the
way a developer would actually type a one-off task, not padded with extra
keywords):

| Domain | Coverage | Risk |
|---|---|---|
| finance | 0% (0/8) | HIGH |
| workflow_automation | 75% (6/8) | MEDIUM |
| chat_assistant | 38% (3/8) | HIGH |
| third_party_integrations | 62% (5/8) | MEDIUM |
| boards_canvas | 50% (4/8) | MEDIUM |
| agent_management | 75% (6/8) | MEDIUM |
| account_settings | 38% (3/8) | HIGH |
| **Total** | **48% (27/56)** | |

`--strict` failed on all 7 domains. Every single failure was "no domain
matched" — not a wrong match, a total miss.

**Root cause, confirmed by direct inspection, not guessed:** the resolver's
routing threshold is `max(2, top_score × 0.66)`. The `max(2, ...)` floor
means **a phrasing needs at least 2 keyword hits to route, no matter how
exact the single hit is.** Example: `"disconnect an integration"` tokenizes
to `["disconnect", "integration"]`; `"integration"` is an exact, unambiguous
keyword for `third_party_integrations` — and it still doesn't route, because
score=1 never clears the floor of 2. This is not a bug in this context.yaml;
it's the resolver behaving exactly as designed. It just means: **any domain
whose natural phrasings tend to carry only one strong signal word will
silently fail to route, regardless of how well-chosen that one keyword is.**
The synthetic sample never surfaced this because its test phrasings
(written by me, alongside the keywords) happened to double up on keywords
almost every time (e.g. "fix billing webhook race condition" hits both
`billing` and `webhook`). Real, natural, single-concept phrasing does not
reliably do that.

**Iteration 1 (the fix loop `/oc-setup`'s own SKILL.md defines — Phase 5,
"patch keywords"):** for each failing phrasing, added the second concept word
already present in that phrasing as a new keyword (e.g. `finance` gained
`dashboard`, `summary`, `report`, `quarter`; `third_party_integrations` gained
`callback`, `disconnect`, `hubspot`, `connection`). One round, no test
phrasings changed, nothing removed:

| Domain | Coverage | Risk |
|---|---|---|
| finance | 50% (4/8) | MEDIUM |
| workflow_automation | 100% (8/8) | LOW |
| chat_assistant | 88% (7/8) | LOW |
| third_party_integrations | 100% (8/8) | LOW |
| boards_canvas | 88% (7/8) | LOW |
| agent_management | 88% (7/8) | LOW |
| account_settings | 88% (7/8) | LOW |
| **Total** | **86% (48/56)** | |

One keyword-patching pass took total coverage from 48% to 86%. Amplification
check: **0 warnings** (was a risk with so many added keywords — didn't
materialize). `--strict` now fails on exactly one domain: `finance`
(`STRICT FAIL: MEDIUM/HIGH phrasing risk: finance`).

**`finance` stayed at 50% on purpose — not patched further.** Its 4 remaining
failures ("list recent transactions", "generate an invoice", "reconcile the
ledger", "track company expenses") each carry exactly one finance-specific
concept word and no natural second one. Closing this gap would mean adding
keywords like "list", "generate", "recent", "track" — generic verbs the
tool's own keyword-quality guide warns against, and the kind of change that
would be cherry-picking the number up rather than fixing anything real. This
is reported as a genuine, unresolved limitation, not smoothed over.

## Result 3 — qualitative spot-check

`"add oauth support for a new hubspot integration"` → matched
`third_party_integrations` (score=3: `integration`, `oauth`, `hubspot`),
correctly surfaced the `oauth_callback_per_vendor` pattern and
`rule-03-oauth-callback-required` — a real invariant of this specific
codebase, not a generic template. `"explain what react hooks are"` (negative
control, a generic dev question unrelated to any domain) → correctly matched
nothing.

## Findings

### Finding A (the headline of this test) — natural single-concept phrasing routinely fails to route

Confirmed structurally, not anecdotally: the `max(2, top_score × 0.66)`
threshold has an unconditional floor of 2 keyword hits. Any task phrased with
only one domain-specific word — which is common, especially for
`routing_only` domains where the whole point is "obvious, low-effort" — will
not route, even with a perfect, unambiguous keyword match. This is a sharper
and more general version of the `team_billing` 80%-coverage observation from
the synthetic benchmark; there it affected 2/30 phrasings, here it affected
29/56 on the first pass. The synthetic sample understated this because its
test phrasings were written by the same person who chose the keywords, at the
same time — a bias this real-world test didn't have.

**This is worth fixing or documenting prominently**, not filing away: either
the wizard's own keyword-generation guidance should explicitly plan for
2-keyword co-occurrence in likely phrasings (not just "5–12 nouns and
verbs"), or the resolver's threshold floor should be revisited for
`routing_only` domains specifically, where a single strong keyword arguably
should be enough.

**Update:** Partially fixed. `resolver.py` now adds `domain_unique_keywords()`
— when nothing clears the standard 2-hit floor at all, a domain whose lone
matched keyword no other domain shares (e.g. `integration` here) routes on
its own, since that's structurally unambiguous evidence, not the kind of
noise the floor exists to filter. Verified against this exact case
(`"disconnect an integration"` now routes), and re-running this sample's
phrasing tests would very likely close some or all of the `finance` gap
described below too, since those 4 residual failures are exactly this
failure mode. Deliberately scoped narrowly, though: the bypass only fires
when nothing else would route anyway — a domain-unique word riding along
in a sentence that already has a dominant match elsewhere (e.g. a task
mentioning `webhook` and, in passing, `hubspot`) does not also get
injected, since that's a genuinely different judgment call this fix does
not attempt to make. See `tests/test_resolver.py` and
`docs/reference.md`'s "Keyword ceiling" note.

### Finding B — the fix loop the product already ships works, and works well

One iteration of `/oc-setup`'s own documented "patch keywords" step took
total coverage from 48% to 86% without touching any test phrasing or
inventing signal that wasn't already in the failing prompts. This is
reassuring: the tool's designed remediation path is not theatre — it
measurably works, at least for the common case of "keyword list was too
sparse." It does not fully close every gap (`finance` here), and users
should expect to hit — and accept — a residual gap rather than force it to
zero with generic keywords.

### Finding C — file/directory inference held up on messy, real structure

Despite the target repo's top-level directory mixing real source with a large
amount of unrelated cruft, path inference for all 28 declared components was
100% accurate on the first attempt. The earlier concern (that a synthetic
sample "sees" exactly the files it wrote) did not turn out to be masking a
weakness here — this held on genuinely unfamiliar, undocumented, sprawling
real code.

### No repeat of the earlier `component_reason()` collision

This sample's architecture components (`page`, `hook`, `api_client`) didn't
collide with the hardcoded Rails-flavored dict in `component_reason()`
(Finding 1 of the earlier report) — at the time this test ran, that dict was
still in place; this test just didn't happen to trigger it, which was itself
informative: the bug was real but silent, firing only when a project's
component names happened to match one of 5 specific Rails words.

**Update:** Finding 1 has since been fixed — `component_reason()` is now
data-driven, reading from `context.yaml`'s own `components.<name>` block
instead of a hardcoded dict (see `docs/nextjs-effectiveness-report.md`'s
Finding 1 resolution note, and
`test_component_reason_reads_from_context_not_hardcoded_rails_text` in
`tests/test_hook_integration.py`). Finding A below is unaffected by that fix
and remains open.

## Recommendation

Finding A remains the priority follow-up — it's more universally impactful
than Finding 1 was: every `routing_only` domain in every project is at risk
of silently under-routing on ordinary single-concept phrasing, not just
projects that happen to name a component `model`. A concrete next step:
audit `/oc-setup` and `/oc-init`'s own generated test phrasings against this
exact failure mode before generating them, not just after (i.e., prefer
phrasings the wizard can verify hit ≥2 keywords, or flag single-keyword-only
phrasings as an inherent risk in the generated `context-decisions.md`).
