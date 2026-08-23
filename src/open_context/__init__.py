"""
Open:Context — zero-LLM context resolver, driven entirely by context.yaml.

Quick start:
    from open_context.resolver import load_context, resolve, format_report
    ctx = load_context("path/to/context.yaml")
    result = resolve("implement member login", context=ctx)
    print(format_report(result))
"""

from .resolver import load_context, resolve, format_report
from .validator import run_phrasing_tests, run_amplification_checks, run_arch_validate
from .schema import validate_context
from .discovery import detect

__all__ = [
    "load_context",
    "resolve",
    "format_report",
    "run_phrasing_tests",
    "run_amplification_checks",
    "run_arch_validate",
    "validate_context",
    "detect",
]
