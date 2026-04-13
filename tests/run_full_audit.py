"""
run_full_audit.py — Runs all three test suites and produces a combined report.

  1. accuracy_audit — scheme JSON internal consistency
  2. web_test       — full-stack POST /results for all 50 case profiles
  3. fuzz_test      — 100 random profiles, engine + web stress test

Usage:
    # Start server first:
    uvicorn web.app:app --port 8000

    python tests/run_full_audit.py [--port 8000] [--fuzz-count 100] [--seed 42]

Output:
    tests/results/accuracy_audit.json
    tests/results/web_test_report.json
    tests/results/fuzz_report.json
    tests/results/full_audit_report.json   ← combined summary
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
RESULTS_DIR = ROOT / "tests" / "results"
RESULTS_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(ROOT))


def check_server(base_url: str) -> bool:
    try:
        r = requests.get(base_url + "/", timeout=5)
        return r.status_code == 200
    except requests.RequestException:
        return False


def run_accuracy_audit() -> dict:
    print("\n" + "━" * 72)
    print("  [1/3]  ACCURACY AUDIT")
    print("━" * 72)
    from tests.accuracy_audit import run as _run
    return _run()


def run_web_test(base_url: str) -> dict:
    print("\n" + "━" * 72)
    print("  [2/3]  WEB TEST (50 cases)")
    print("━" * 72)
    from tests.web_test import run as _run
    report_cases = _run(base_url)
    # Compute summary stats
    n = len(report_cases)
    server_errors = sum(1 for r in report_cases if r.get("server_error"))
    render_errors = sum(1 for r in report_cases if r.get("render_error"))
    status_mismatches = sum(r["summary"]["status_mismatches"] for r in report_cases)
    missing_cards = sum(r["summary"]["missing_cards"] for r in report_cases)
    verdict = "PASS" if (server_errors + render_errors + status_mismatches + missing_cards) == 0 else "FAIL"
    return {
        "verdict": verdict,
        "cases_tested": n,
        "server_errors": server_errors,
        "render_errors": render_errors,
        "status_mismatches": status_mismatches,
        "missing_cards": missing_cards,
        "cases": report_cases,
    }


def run_fuzz_test(base_url: str, count: int, seed: int) -> dict:
    print("\n" + "━" * 72)
    print(f"  [3/3]  FUZZ TEST ({count} random profiles, seed={seed})")
    print("━" * 72)
    from tests.fuzz_test import run as _run
    return _run(base_url, count, seed)


def main():
    parser = argparse.ArgumentParser(description="Kalam full audit runner")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--fuzz-count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-web", action="store_true", help="Run accuracy audit only (no server needed)")
    args = parser.parse_args()
    base = args.base_url or f"http://localhost:{args.port}"

    if not args.skip_web:
        if not check_server(base):
            print(f"\nERROR: Cannot reach server at {base}")
            print("  Start it with:  uvicorn web.app:app --port 8000")
            sys.exit(1)
        print(f"\nServer at {base} — OK")

    t0 = time.time()
    combined: dict = {"base_url": base, "verdicts": {}}

    # ── 1. Accuracy audit ──────────────────────────────────────────────────────
    acc = run_accuracy_audit()
    combined["accuracy_audit"] = {
        "verdict": acc["verdict"],
        "pass": acc["pass"],
        "fail": acc["fail"],
        "total": acc["total"],
        "issues_count": len(acc["all_issues"]),
        "warnings_count": len(acc["all_warnings"]),
    }
    combined["verdicts"]["accuracy_audit"] = acc["verdict"]

    # Save individual
    with open(RESULTS_DIR / "accuracy_audit.json", "w") as f:
        json.dump(acc, f, indent=2)

    if not args.skip_web:
        # ── 2. Web test ────────────────────────────────────────────────────────
        web = run_web_test(base)
        combined["web_test"] = {
            "verdict": web["verdict"],
            "cases_tested": web["cases_tested"],
            "server_errors": web["server_errors"],
            "render_errors": web["render_errors"],
            "status_mismatches": web["status_mismatches"],
            "missing_cards": web["missing_cards"],
        }
        combined["verdicts"]["web_test"] = web["verdict"]

        with open(RESULTS_DIR / "web_test_report.json", "w") as f:
            json.dump({"elapsed_s": 0, "cases": web["cases"]}, f, indent=2)

        # ── 3. Fuzz test ───────────────────────────────────────────────────────
        fuzz = run_fuzz_test(base, args.fuzz_count, args.seed)
        combined["fuzz_test"] = fuzz["summary"]
        combined["verdicts"]["fuzz_test"] = fuzz["summary"]["verdict"]

        with open(RESULTS_DIR / "fuzz_report.json", "w") as f:
            json.dump(fuzz, f, indent=2)

    # ── Combined verdict ───────────────────────────────────────────────────────
    all_verdicts = list(combined["verdicts"].values())
    combined["overall_verdict"] = "PASS" if all(v == "PASS" for v in all_verdicts) else "FAIL"
    combined["elapsed_s"] = round(time.time() - t0, 2)

    # ── Print final summary ────────────────────────────────────────────────────
    print("\n" + "═" * 72)
    print("  FULL AUDIT SUMMARY")
    print("═" * 72)
    for suite, verdict in combined["verdicts"].items():
        icon = "✅" if verdict == "PASS" else "❌"
        print(f"  {icon}  {suite:<30}  {verdict}")
    print(f"\n  OVERALL: {combined['overall_verdict']}  (took {combined['elapsed_s']}s)")
    print("═" * 72 + "\n")

    out = RESULTS_DIR / "full_audit_report.json"
    with open(out, "w") as f:
        json.dump(combined, f, indent=2)
    print(f"  Combined report → {out.relative_to(ROOT)}\n")

    sys.exit(0 if combined["overall_verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
