# Ingestion Checklist

Every ingestion script pulls from an external, third-party API. Before
merging a new or modified ingestion script:

- **Idempotent by construction.** The scheduler retries a failed run
  automatically. An ingestion script must be safe to run twice on the
  same source window — upsert on the source system's natural key, never
  a plain append-only insert. A duplicate row from a retried run is a
  silent data-correctness bug, not a visible crash, which is why this is
  a checklist item and not just a code-review nit.
- **Bounded time window per run.** Never ingest "everything since the
  beginning of time" as the default — pass an explicit `--since`/`--until`
  window so a re-run has a bounded, predictable cost.
