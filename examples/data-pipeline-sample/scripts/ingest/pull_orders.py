"""Pulls order data from the upstream orders API into the warehouse.

Idempotent: upserts on the upstream order id, never a plain append.
See docs/rules/ingestion-checklist.md.
"""
