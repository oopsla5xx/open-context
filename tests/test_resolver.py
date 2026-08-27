"""
Unit tests for resolver.py's domain-level threshold logic — specifically
the domain-unique-keyword floor bypass (see resolver.py's resolve()
docstring comment and domain_unique_keywords()'s docstring for the
real-world routing gap this fixes: docs/nextjs-real-world-test-report.md,
Finding A).

Direct-import unit tests, not subprocess integration tests like
test_hook_integration.py — resolver.py's threshold logic is a plain
deterministic function with no hook/CLI-boundary concerns to exercise as
a subprocess.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PLUGIN_ROOT / "src"))
sys.path.insert(0, str(PLUGIN_ROOT / "vendor"))

from open_context.resolver import domain_unique_keywords, resolve  # noqa: E402

BASE_CTX = {"project": {"name": "demo", "default_actor": "user"}, "architecture": {}, "rules": []}


def _ctx(domains):
    return {**BASE_CTX, "domains": domains}


def _matched(result):
    return [d["name"] for d in result["matched_domains"]]


def test_sole_unambiguous_single_keyword_now_routes():
    """The exact failure case from the real-world test report: an exact,
    non-competing single-keyword match ("disconnect an integration") must
    route even though its score of 1 never clears the standard floor of 2."""
    ctx = _ctx([
        {"name": "third_party_integrations", "keywords": ["integration", "oauth", "hubspot", "callback"]},
        {"name": "billing", "keywords": ["billing", "invoice", "webhook"]},
    ])
    assert _matched(resolve("disconnect an integration", context=ctx)) == ["third_party_integrations"]


def test_shared_keyword_single_match_still_filtered():
    """A keyword shared by more than one domain is not unambiguous — a lone
    match on it must still be filtered out by the standard floor, same as
    before this fix."""
    ctx = _ctx([
        {"name": "accounts", "keywords": ["user", "signup", "password"]},
        {"name": "billing", "keywords": ["user", "invoice", "webhook"]},
    ])
    assert _matched(resolve("list all user", context=ctx)) == []


def test_dominant_match_elsewhere_not_dragged_down_by_incidental_unique_keyword():
    """Regression guard: when a domain already clears the standard floor
    (top_score >= 2), an unrelated domain's incidental domain-unique
    keyword riding along in the same sentence must NOT also inject that
    domain. Confirmed against the real rails-hmvc-sample context.yaml —
    'renew book loan' must resolve to borrowing_management only, not also
    catalog_management just because 'book' happens to be catalog's only
    claim on that word."""
    ctx = _ctx([
        {"name": "catalog_management", "keywords": ["book", "author", "genre"]},
        {"name": "borrowing_management", "keywords": ["borrow", "renew", "loan"]},
    ])
    assert _matched(resolve("renew book loan", context=ctx)) == ["borrowing_management"]


def test_sole_domain_single_keyword_routes():
    """A context.yaml with only one domain: any of its keywords is trivially
    unique (no other domain to share it with), so a single match routes."""
    ctx = _ctx([{"name": "catalog", "keywords": ["book", "author", "genre"]}])
    assert _matched(resolve("show the book", context=ctx)) == ["catalog"]


def test_normal_two_hit_threshold_unaffected():
    """Baseline regression guard: ordinary 2+-keyword matches still route
    exactly as before this fix."""
    ctx = _ctx([{"name": "billing", "keywords": ["billing", "invoice", "webhook"]}])
    assert _matched(resolve("fix billing webhook race condition", context=ctx)) == ["billing"]


def test_domain_unique_keywords_helper():
    domains = [
        {"name": "a", "keywords": ["shared", "only_a"]},
        {"name": "b", "keywords": ["shared", "only_b"]},
    ]
    result = domain_unique_keywords(domains)
    assert result["a"] == {"only_a"}
    assert result["b"] == {"only_b"}


def test_domain_unique_keywords_no_domains():
    assert domain_unique_keywords([]) == {}
