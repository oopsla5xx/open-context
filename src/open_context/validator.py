"""
Open:Context Validator — phrasing coverage, amplification risk, and
file-existence checks against the resolver and context model.

All functions return plain dicts/lists — no argparse, no print, no sys.exit.
The CLI layer (cli.py) handles formatting and exit codes.
"""

from pathlib import Path

from .resolver import resolve


# ─────────────────────────────────────────────────────────────────────────────
# Phrasing coverage validator
# ─────────────────────────────────────────────────────────────────────────────

AMPLIFICATION_DANGER = 4
AMPLIFICATION_NOTE = 3


def load_phrasings(tests_dir: "Path | str", domain: str) -> list[tuple[str, str]]:
    """
    Load phrasing test pairs from <tests_dir>/<domain>.txt.
    Returns list of (phrasing, expected_domain) tuples.
    Lines starting with # are comments. Blank lines are skipped.
    """
    path = Path(tests_dir) / f"{domain}.txt"
    if not path.exists():
        return []
    pairs = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            continue
        phrasing, expected = line.split("|", 1)
        pairs.append((phrasing.strip(), expected.strip()))
    return pairs


def run_phrasing_tests(ctx: dict, tests_dir: "Path | str") -> dict:
    """
    Run phrasing tests for all domains defined in ctx, plus any subtype that
    has its own <subtype_name>.txt test file.

    A subtype test file checks routing into result["matched_subtypes"]
    (not matched_domains) — subtype names live in a separate namespace from
    domain names, so a domain-level check would never see them. Subtypes
    with no dedicated test file are skipped (not reported as UNTESTED) since
    per-subtype tests are optional, unlike domain tests.

    Returns:
      {
        "by_domain": { domain_name: { tested, correct, pct, risk, failures } },
        "by_subtype": { subtype_name: { ..., parent_domain } },  # only if tested
        "total_tested": int,
        "total_correct": int,
        "total_pct": float,
      }
    """
    domain_names = [d["name"] for d in ctx.get("domains", [])]
    results = {}
    subtype_results = {}
    total_tested = total_correct = 0

    for domain in domain_names:
        pairs = load_phrasings(tests_dir, domain)
        tested = len(pairs)
        correct = 0
        failures = []

        for phrase, expected in pairs:
            result = resolve(phrase, context=ctx)
            matched = [d["name"] for d in result["matched_domains"]]
            if expected in matched:
                correct += 1
            else:
                failures.append({"phrase": phrase, "expected": expected, "got": matched})

        pct = (correct / tested * 100) if tested > 0 else 0.0
        risk = _risk_label(pct) if tested > 0 else "UNTESTED"
        results[domain] = {
            "tested": tested,
            "correct": correct,
            "pct": pct,
            "risk": risk,
            "failures": failures,
        }
        total_tested += tested
        total_correct += correct

    for domain in ctx.get("domains", []):
        for st in domain.get("subtypes", []):
            st_name = st["name"]
            pairs = load_phrasings(tests_dir, st_name)
            tested = len(pairs)
            if tested == 0:
                continue
            correct = 0
            failures = []

            for phrase, expected in pairs:
                result = resolve(phrase, context=ctx)
                matched = [si["name"] for si in result["matched_subtypes"]]
                if expected in matched:
                    correct += 1
                else:
                    failures.append({"phrase": phrase, "expected": expected, "got": matched})

            pct = (correct / tested * 100) if tested > 0 else 0.0
            subtype_results[st_name] = {
                "tested": tested,
                "correct": correct,
                "pct": pct,
                "risk": _risk_label(pct),
                "failures": failures,
                "parent_domain": domain["name"],
            }
            total_tested += tested
            total_correct += correct

    return {
        "by_domain": results,
        "by_subtype": subtype_results,
        "total_tested": total_tested,
        "total_correct": total_correct,
        "total_pct": (total_correct / total_tested * 100) if total_tested > 0 else 0.0,
    }


def _risk_label(pct: float) -> str:
    if pct < 50:
        return "HIGH"
    if pct < 80:
        return "MEDIUM"
    return "LOW"


def _find_shared_root_pairs(keywords: list[str]) -> list[tuple[str, str, str]]:
    pairs = []
    seen = set()
    for i, kw1 in enumerate(keywords):
        parts1 = set(kw1.split("_"))
        for j, kw2 in enumerate(keywords):
            if i == j:
                continue
            parts2 = set(kw2.split("_"))
            shared = parts1 & parts2
            prefix = kw1.startswith(kw2) or kw2.startswith(kw1)
            if shared or prefix:
                key = tuple(sorted([kw1, kw2]))
                if key not in seen:
                    seen.add(key)
                    root = min(shared, key=len) if shared else min(kw1, kw2, key=len)
                    pairs.append((kw1, kw2, root))
    return pairs


def run_amplification_checks(ctx: dict) -> list[dict]:
    """
    Check for amplification risk: single tokens matching multiple keywords in
    the same domain raise the threshold and may block legitimate co-routing.
    Returns list of findings with level "WARNING" or "NOTE".
    """
    findings = []
    for domain in ctx.get("domains", []):
        kws = domain.get("keywords", [])
        seen_roots = set()
        for kw1, kw2, root in _find_shared_root_pairs(kws):
            if root in seen_roots:
                continue
            seen_roots.add(root)
            result = resolve(root, context=ctx)
            score = next(
                (d["score"] for d in result["matched_domains"] if d["name"] == domain["name"]),
                0,
            )
            if score >= AMPLIFICATION_NOTE:
                level = "WARNING" if score >= AMPLIFICATION_DANGER else "NOTE"
                findings.append({
                    "domain": domain["name"],
                    "root_token": root,
                    "shared_keywords": [kw1, kw2],
                    "score": score,
                    "level": level,
                    "detail": (
                        f"Token '{root}' matches {score} keywords in {domain['name']} "
                        f"({kw1}, {kw2}, ...). "
                        + ("Threshold may block co-routing." if level == "WARNING" else "Monitor.")
                    ),
                })
    return findings


# ─────────────────────────────────────────────────────────────────────────────
# File-existence check
# ─────────────────────────────────────────────────────────────────────────────

def check_file_existence(ctx: dict, repo_root: "Path | str") -> dict:
    """
    Verify that every path declared in related_components (domain level and
    subtype level) exists under repo_root.

    Returns:
      {
        "repo_root": str,
        "by_domain": {
          domain_name: {
            "declared": list[str],
            "found":    list[str],
            "missing":  list[str],
          }
        },
        "total_declared": int,
        "total_found":    int,
        "total_missing":  int,
        "repo_mismatch":  bool,   # True when total_found == 0 and total_declared > 0
      }
    """
    root = Path(repo_root).resolve()
    by_domain: dict = {}
    total_declared = total_found = total_missing = 0

    for domain in ctx.get("domains", []):
        name = domain["name"]

        # Collect paths from domain level + all subtype levels, deduped.
        seen: set = set()
        paths: list = []
        for p in domain.get("related_components", []):
            if p not in seen:
                seen.add(p)
                paths.append(p)
        for st in domain.get("subtypes", []):
            for p in st.get("related_components", []):
                if p not in seen:
                    seen.add(p)
                    paths.append(p)

        found = []
        missing = []
        for p in paths:
            if (root / p.lstrip("/")).exists():
                found.append(p)
            else:
                missing.append(p)

        by_domain[name] = {"declared": paths, "found": found, "missing": missing}
        total_declared += len(paths)
        total_found += len(found)
        total_missing += len(missing)

    return {
        "repo_root": str(root),
        "by_domain": by_domain,
        "total_declared": total_declared,
        "total_found": total_found,
        "total_missing": total_missing,
        "repo_mismatch": total_declared > 0 and total_found == 0,
    }

