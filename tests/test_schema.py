"""
Unit tests for schema.py (context.yaml structure validation).

Direct-import unit tests, not subprocess integration tests like
test_hook_integration.py — schema.py is a plain deterministic module
with no hook/CLI-boundary concerns to exercise as a subprocess.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PLUGIN_ROOT / "src"))
sys.path.insert(0, str(PLUGIN_ROOT / "vendor"))

from open_context.schema import validate_context  # noqa: E402

MINIMAL_VALID_CTX = {
    "project": {"name": "demo"},
    "architecture": {"flow": ["controller", "model"]},
    "domains": [{"name": "widgets", "keywords": ["widget"]}],
    "rules": [],
}


def test_minimal_context_is_valid():
    assert validate_context(MINIMAL_VALID_CTX) == []


def test_rule_missing_source_is_rejected():
    ctx = copy.deepcopy(MINIMAL_VALID_CTX)
    ctx["rules"] = [{"id": "r1", "description": "no bare raises"}]

    errors = validate_context(ctx)
    assert any("rules[0]" in e and "source" in e for e in errors)


def test_rule_with_source_is_accepted():
    ctx = copy.deepcopy(MINIMAL_VALID_CTX)
    ctx["rules"] = [{"id": "r1", "description": "no bare raises", "source": "AGENTS.md"}]

    assert validate_context(ctx) == []


def test_domain_pattern_missing_source_is_rejected():
    ctx = copy.deepcopy(MINIMAL_VALID_CTX)
    ctx["domains"][0]["patterns"] = [{"id": "p1", "description": "always paginate"}]

    errors = validate_context(ctx)
    assert any("domains[0]" in e and "patterns[0]" in e and "source" in e for e in errors)


def test_subtype_pattern_missing_source_is_rejected():
    ctx = copy.deepcopy(MINIMAL_VALID_CTX)
    ctx["domains"][0]["subtypes"] = [{
        "name": "widget_search",
        "keywords": ["search"],
        "patterns": [{"id": "p1", "description": "paginate results"}],
    }]

    errors = validate_context(ctx)
    assert any("subtypes[0]" in e and "patterns[0]" in e and "source" in e for e in errors)


def test_pattern_with_source_is_accepted():
    ctx = copy.deepcopy(MINIMAL_VALID_CTX)
    ctx["domains"][0]["patterns"] = [{"id": "p1", "description": "always paginate", "source": "docs/api.md"}]

    assert validate_context(ctx) == []


def test_architecture_flow_optional():
    ctx = copy.deepcopy(MINIMAL_VALID_CTX)
    ctx["architecture"] = {}

    assert validate_context(ctx) == []


def test_architecture_flow_absent_key_is_valid():
    ctx = copy.deepcopy(MINIMAL_VALID_CTX)
    del ctx["architecture"]["flow"]

    assert validate_context(ctx) == []


def test_architecture_flow_wrong_type_is_rejected():
    ctx = copy.deepcopy(MINIMAL_VALID_CTX)
    ctx["architecture"]["flow"] = "controller"

    errors = validate_context(ctx)
    assert any("architecture.flow" in e for e in errors)
