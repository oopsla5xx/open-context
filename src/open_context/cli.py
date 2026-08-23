#!/usr/bin/env python3
"""
Open:Context CLI

Commands:
  resolve <task> --context PATH [--json]
      Route a task description to the relevant context layers.

  validate --context PATH [--tests PATH] [--repo PATH] [--strict] [--json]
      Run phrasing coverage + amplification safety + file-existence check.

  architecture validate [--repo PATH] [--path DIR] [--json]
      Run 6 HMVC architecture compliance rules against the codebase.

  detect [--repo PATH] [--json]
      Detect language/framework/version/package-manager/database/ORM/test
      framework from structured config files (Gemfile, package.json,
      pyproject.toml/requirements.txt), with a per-field confidence score.
      Non-recursive: only reads files directly under --repo.

  architecture discover [--repo PATH] [--app-dir DIR] [--json]
      Discover the REAL component chain (Rails-family apps) by scanning
      app/ for directories and call-evidence between them — not a fixed
      archetype. Proposes a chain + confidence; never writes context.yaml.
"""

import sys
import json
import argparse
from pathlib import Path

import yaml

from .resolver import load_context, resolve, format_report
from .validator import run_phrasing_tests, run_amplification_checks, run_arch_validate, check_file_existence
from .schema import validate_context
from .discovery import detect
from .architecture_discovery import discover_architecture, assess_confidence


# ─────────────────────────────────────────────────────────────────────────────
# resolve
# ─────────────────────────────────────────────────────────────────────────────

def cmd_resolve(args):
    ctx = _load_and_validate(args.context)
    result = resolve(" ".join(args.task), context=ctx)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(format_report(result))


# ─────────────────────────────────────────────────────────────────────────────
# validate (phrasing coverage + amplification)
# ─────────────────────────────────────────────────────────────────────────────

def cmd_validate(args):
    ctx = _load_and_validate(args.context)
    context_path = Path(args.context)
    tests_dir = Path(args.tests) if args.tests else context_path.parent / "tests"
    repo_root = Path(args.repo).resolve() if args.repo else Path.cwd()

    sep = "─" * 72
    phrasing_results = run_phrasing_tests(ctx, tests_dir)
    by_domain = phrasing_results["by_domain"]
    ampl_findings = run_amplification_checks(ctx)
    file_check = check_file_existence(ctx, repo_root)

    # ── Phrasing coverage ─────────────────────────────────────────────────────
    print(sep)
    print("open-context validate — Phrasing Coverage + Amplification Safety")
    print(sep)

    print(f"\n{'Domain':<32} {'Tested':>6} {'Correct':>7} {'Coverage':>9} {'Risk':<8}")
    print("-" * 64)
    for domain, r in by_domain.items():
        if r["tested"] == 0:
            print(f"  {domain:<30} {'—':>6} {'—':>7} {'UNTESTED':>9} {'—':<8}")
        else:
            print(
                f"  {domain:<30} {r['tested']:>6} {r['correct']:>7} "
                f"{r['pct']:>8.0f}% {r['risk']:<8}"
            )
    print("-" * 64)
    total = phrasing_results
    print(
        f"  {'TOTAL':<30} {total['total_tested']:>6} {total['total_correct']:>7} "
        f"{total['total_pct']:>8.0f}%"
    )

    by_subtype = phrasing_results.get("by_subtype", {})
    if by_subtype:
        print(f"\n{'Subtype (parent)':<32} {'Tested':>6} {'Correct':>7} {'Coverage':>9} {'Risk':<8}")
        print("-" * 64)
        for st, r in by_subtype.items():
            label = f"{st} ({r['parent_domain']})"
            print(
                f"  {label:<30} {r['tested']:>6} {r['correct']:>7} "
                f"{r['pct']:>8.0f}% {r['risk']:<8}"
            )
        print("-" * 64)

    all_failures = [f for r in by_domain.values() for f in r["failures"]]
    all_failures += [f for r in by_subtype.values() for f in r["failures"]]
    if all_failures:
        print(f"\n[FAILURES — {len(all_failures)} total]")
        for f in all_failures:
            print(f"  FAIL  \"{f['phrase']}\"")
            print(f"        expected: {f['expected']}")
            print(f"        got:      {f['got'] or '(no domain matched)'}")
    else:
        print("\n[FAILURES] none — all phrasings routed correctly")

    # ── Amplification safety ──────────────────────────────────────────────────
    print(f"\n{sep}")
    print("Amplification Safety Check")
    print(sep)

    if not ampl_findings:
        print("  No amplification issues detected.")
    else:
        warnings = [f for f in ampl_findings if f["level"] == "WARNING"]
        notes = [f for f in ampl_findings if f["level"] == "NOTE"]
        if warnings:
            print(f"\n  [{len(warnings)} WARNING(s)]")
            for f in warnings:
                print(f"  ⚠  {f['domain']} | root='{f['root_token']}' | score={f['score']}")
                print(f"     {f['detail']}")
        if notes:
            print(f"\n  [{len(notes)} NOTE(s)]")
            for f in notes:
                print(f"  ·  {f['domain']} | root='{f['root_token']}' | score={f['score']}")
                print(f"     {f['detail']}")

    # ── File existence check ──────────────────────────────────────────────────
    print(f"\n{sep}")
    print(f"File Existence Check  (repo: {file_check['repo_root']})")
    print(sep)

    if file_check["repo_mismatch"]:
        print(
            f"  ⚠  POSSIBLE --repo MISMATCH — 0 of {file_check['total_declared']} declared "
            f"paths found under {file_check['repo_root']}. Check --repo is correct."
        )
    elif file_check["total_declared"] == 0:
        print("  No related_components declared — nothing to check.")
    else:
        print(f"\n  {'Domain':<30} {'Declared':>8} {'Found':>6} {'Missing':>8}")
        print("  " + "-" * 56)
        for domain, r in file_check["by_domain"].items():
            if not r["declared"]:
                continue
            marker = "⚠ " if r["missing"] else "  "
            print(
                f"  {marker}{domain:<28} {len(r['declared']):>8} "
                f"{len(r['found']):>6} {len(r['missing']):>8}"
            )
        print("  " + "-" * 56)
        print(
            f"  {'TOTAL':<30} {file_check['total_declared']:>8} "
            f"{file_check['total_found']:>6} {file_check['total_missing']:>8}"
        )

        if file_check["total_missing"] > 0:
            print("\n  Missing paths:")
            for domain, r in file_check["by_domain"].items():
                for p in r["missing"]:
                    print(f"    [{domain}] {p} — not found")
        else:
            print(f"\n  All {file_check['total_found']} declared paths found ✓")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{sep}")
    pass_count = total["total_correct"]
    warn_count = len([f for f in ampl_findings if f["level"] == "WARNING"])
    missing_count = file_check["total_missing"]
    print(
        f"RESULT  {pass_count}/{total['total_tested']} phrasings PASS "
        f"({total['total_pct']:.0f}%)"
        f"  |  {warn_count} amplification warning(s)"
        f"  |  {missing_count} missing path(s)"
    )
    print(sep)

    if args.json:
        print(json.dumps({
            "phrasing_results": phrasing_results,
            "amplification_findings": ampl_findings,
            "file_existence": file_check,
        }, indent=2, default=str))

    # ── --strict exit code ────────────────────────────────────────────────────
    if args.strict:
        fail_reasons = []
        if file_check["repo_mismatch"] or missing_count > 0:
            fail_reasons.append(f"{missing_count} missing path(s)")
        risky = [d for d, r in by_domain.items() if r.get("risk") in ("MEDIUM", "HIGH")]
        risky += [st for st, r in by_subtype.items() if r.get("risk") in ("MEDIUM", "HIGH")]
        if risky:
            fail_reasons.append(f"MEDIUM/HIGH phrasing risk: {', '.join(risky)}")
        if fail_reasons:
            print(f"STRICT FAIL: {'; '.join(fail_reasons)}", file=sys.stderr)
            sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# architecture validate
# ─────────────────────────────────────────────────────────────────────────────

def cmd_arch_validate(args):
    base = Path(args.repo).resolve() if args.repo else Path.cwd()
    path_filter = Path(args.path).resolve() if args.path else None
    sep = "─" * 72

    print(sep)
    print("open-context architecture validate")
    print(f"Scope: {path_filter or base}")
    print(sep)

    report = run_arch_validate(base, path_filter)
    total_violations = report["total_violations"]
    total_files_checked = report["total_files_checked"]

    print()
    for result in report["results"]:
        rule = result["rule"]
        vcount = sum(len(v["hits"]) for v in result["violations"])
        status = "✓" if vcount == 0 else "✗"
        print(f"  {status} [{rule['id']}] {rule['name']}")
        if vcount > 0:
            for rv in result["violations"]:
                for hit in rv["hits"]:
                    loc = f":{hit['line']}" if hit["line"] else ""
                    print(f"      File: {rv['file']}{loc}")
                    if hit["code"]:
                        print(f"      Code: {hit['code'].strip()}")
                    print(f"      Issue: {hit['detail']}")
                    print()

    print(sep)
    checked_label = f"{total_files_checked} files checked"
    if total_violations == 0:
        print(f"RESULT  ✓ All rules PASS  ({checked_label})")
    else:
        print(f"RESULT  ✗ {total_violations} violation(s) found  ({checked_label})")
    print(sep)

    if args.json:
        print(json.dumps({
            "scope": report["scope"],
            "total_violations": total_violations,
            "results": [
                {
                    "id": r["rule"]["id"],
                    "name": r["rule"]["name"],
                    "files_checked": r["files_checked"],
                    "violations": r["violations"],
                }
                for r in report["results"]
            ],
        }, indent=2, default=str))

    if total_violations > 0:
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# architecture discover
# ─────────────────────────────────────────────────────────────────────────────

def cmd_arch_discover(args):
    base = Path(args.repo).resolve() if args.repo else Path.cwd()
    result = discover_architecture(base, app_subdir=args.app_dir)
    sep = "─" * 72

    print(sep)
    print(f"open-context architecture discover — {result['repo']} ({result['app_subdir']}/)")
    print(sep)

    if not result["components"]:
        print(f"\n  {result.get('note', 'no components found')}")
    else:
        print(f"\n  {'Component':<16} {'.rb files':>9}  {'external?':<10}")
        print("  " + "-" * 40)
        for name, count in result["components"].items():
            ext = "external" if name in result["external_components"] else ""
            print(f"  {name:<16} {count:>9}  {ext:<10}")

        print(f"\n  Suggested flow: {' -> '.join(result['suggested_flow']) or '(no connected components)'}")
        if result["cycle_detected"]:
            print(f"  ⚠ Cycle detected among: {', '.join(result['cycle_detected'])} — "
                  f"order among these is not linear, reported as-is")
        if result["entry_candidates"]:
            print(f"  Entry candidate(s): {', '.join(result['entry_candidates'])}")
        if result["terminal_candidates"]:
            print(f"  Terminal candidate(s): {', '.join(result['terminal_candidates'])}")
        if result["unconnected"]:
            print(f"  Unconnected (no call-evidence in or out): {', '.join(result['unconnected'])}")

        print(f"\n  {'Edge':<28} {'Confidence':>10}  {'Evidence'}")
        print("  " + "-" * 64)
        for e in result["edges"]:
            edge_label = f"{e['from']} -> {e['to']}"
            print(f"  {edge_label:<28} {e['confidence']:>9.0%}  {e['matched_files']}/{e['total_files']} files")

        assessment = assess_confidence(result)
        print()
        if assessment["propose"]:
            print("  PROPOSE: yes — suggested flow above is a reasonable proposal")
        else:
            print("  PROPOSE: no — ask directly instead of proposing a flow")
            for reason in assessment["reasons"]:
                print(f"    - {reason}")

    print(sep)

    if args.json:
        print(json.dumps(result, indent=2, default=str))


# ─────────────────────────────────────────────────────────────────────────────
# detect
# ─────────────────────────────────────────────────────────────────────────────

def cmd_detect(args):
    repo = Path(args.repo).resolve() if args.repo else Path.cwd()
    result = detect(repo)
    sep = "─" * 72

    print(sep)
    print(f"open-context detect — {result['repo']}")
    print(sep)

    if not result["ecosystems"]:
        print("\n  No recognized manifest found directly under this path")
        print("  (Gemfile / package.json / pyproject.toml / requirements.txt).")
    for eco in result["ecosystems"]:
        print(f"\n[{eco['ecosystem'].upper()}]")
        if eco.get("error"):
            print(f"  ⚠ {eco['error']}")
            continue
        for key, f in eco["fields"].items():
            if key.startswith("_"):
                continue
            pct = f"{f['confidence'] * 100:.0f}%"
            print(f"  {key:<18} {str(f['value']):<26} confidence={pct:<5} source={f['source']}")
        conflict = eco["fields"].get("_source_conflict_note")
        if conflict:
            print(f"  ⚠ {conflict}")

    if len(result["ecosystems"]) > 1:
        print(f"\n  Note: {len(result['ecosystems'])} ecosystems detected directly under this path — reported "
              f"independently, no merge/priority logic applied.")

    print(sep)

    if args.json:
        print(json.dumps(result, indent=2, default=str))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_and_validate(context_path: str) -> dict:
    try:
        ctx = load_context(context_path)
    except FileNotFoundError:
        print(f"error: context file not found: {context_path}", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"error: invalid YAML in {context_path}:", file=sys.stderr)
        mark = getattr(e, "problem_mark", None)
        problem = getattr(e, "problem", None) or str(e)
        if mark is not None:
            print(f"  line {mark.line + 1}, column {mark.column + 1}: {problem}", file=sys.stderr)
        else:
            print(f"  {problem}", file=sys.stderr)
        sys.exit(1)
    errors = validate_context(ctx)
    if errors:
        print("error: invalid context.yaml:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)
    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# Argument parser + entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="open-context",
        description="Open:Context CLI — context resolver (any framework) + Rails HMVC architecture validator",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # resolve
    p_resolve = sub.add_parser("resolve", help="Resolve a task to relevant context")
    p_resolve.add_argument("task", nargs="+", help="Task description")
    p_resolve.add_argument("--context", metavar="PATH", required=True,
                           help="Path to context.yaml")
    p_resolve.add_argument("--json", action="store_true", help="Output raw JSON")
    p_resolve.set_defaults(func=cmd_resolve)

    # validate (phrasing coverage)
    p_validate = sub.add_parser("validate", help="Run phrasing coverage + amplification safety check")
    p_validate.add_argument("--context", metavar="PATH", required=True,
                            help="Path to context.yaml")
    p_validate.add_argument("--tests", metavar="PATH", default=None,
                            help="Path to tests directory (default: <context-dir>/tests/)")
    p_validate.add_argument("--repo", metavar="PATH", default=None,
                            help="Repo root for file-existence check (default: current directory)")
    p_validate.add_argument("--strict", action="store_true",
                            help="Exit 1 if any paths are missing or phrasing risk is MEDIUM/HIGH")
    p_validate.add_argument("--json", action="store_true", help="Also print JSON results")
    p_validate.set_defaults(func=cmd_validate)

    # architecture
    p_arch = sub.add_parser("architecture", help="Architecture compliance checks")
    arch_sub = p_arch.add_subparsers(dest="arch_command", required=True)

    p_arch_val = arch_sub.add_parser("validate", help="Run 6 HMVC architecture rules against codebase")
    p_arch_val.add_argument("--repo", metavar="PATH", default=None,
                            help="Rails repo root to scan (default: current directory)")
    p_arch_val.add_argument("--path", metavar="DIR", default=None,
                            help="Limit scan to this subdirectory")
    p_arch_val.add_argument("--json", action="store_true", help="Also print JSON results")
    p_arch_val.set_defaults(func=cmd_arch_validate)

    p_arch_disc = arch_sub.add_parser(
        "discover",
        help="Discover the real component chain from app/ call-evidence (proposal only, never writes context.yaml)",
    )
    p_arch_disc.add_argument("--repo", metavar="PATH", default=None,
                             help="Repo root to scan (default: current directory)")
    p_arch_disc.add_argument("--app-dir", metavar="DIR", default="app",
                             help="Subdirectory to scan for components (default: app)")
    p_arch_disc.add_argument("--json", action="store_true", help="Also print JSON results")
    p_arch_disc.set_defaults(func=cmd_arch_discover)

    # detect
    p_detect = sub.add_parser("detect", help="Detect stack (language/framework/version/db/orm/tests)")
    p_detect.add_argument("--repo", metavar="PATH", default=None,
                          help="Repo path to scan, non-recursive (default: current directory)")
    p_detect.add_argument("--json", action="store_true", help="Also print JSON results")
    p_detect.set_defaults(func=cmd_detect)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
