"""Standalone script: loads all case_XX.json fixtures, runs the eligibility engine,
prints a summary table, and saves a detailed report to tests/results/50_cases_report.json.

Usage:
    python tests/run_50_cases.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Make project root importable regardless of working directory
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import ValidationError

from src.models.user_profile import UserProfile
from src.models.scheme import Scheme
from src.engine.rule_engine import evaluate_scheme
from src.engine.confidence import ConfidenceScorer, MatchStatus
from src.loader import load_all_schemes

FIXTURES_DIR = ROOT / "tests" / "fixtures" / "profiles"
RESULTS_DIR = ROOT / "tests" / "results"
REPORT_PATH = RESULTS_DIR / "50_cases_report.json"

# ── Expected results for key (case_id, scheme_id) pairs ──────────────────────
# These are used to flag mismatches in the summary.
EXPECTED: dict[str, dict[str, MatchStatus]] = {
    "case_01": {"pm_kisan": MatchStatus.ELIGIBLE, "mgnrega": MatchStatus.ELIGIBLE},
    "case_02": {
        "pm_kisan": MatchStatus.INELIGIBLE,
        "mgnrega": MatchStatus.INELIGIBLE,
        "apy": MatchStatus.INELIGIBLE,
    },
    "case_03": {
        "nsap_ignoaps": MatchStatus.ELIGIBLE,
        "nsap_ignwps": MatchStatus.ELIGIBLE,
        "pm_kisan": MatchStatus.INELIGIBLE,
    },
    "case_04": {"pmjdy": MatchStatus.ELIGIBLE},
    "case_05": {
        "pm_svanidhi": MatchStatus.ELIGIBLE,
        "mgnrega": MatchStatus.INELIGIBLE,
    },
    "case_06": {"pm_vishwakarma": MatchStatus.ELIGIBLE},
    "case_07": {"pmmvy": MatchStatus.ELIGIBLE},
    "case_08": {"sukanya_samriddhi": MatchStatus.ELIGIBLE},
    "case_09": {"nsap_igndps": MatchStatus.ELIGIBLE},
    "case_10": {
        "pm_kisan": MatchStatus.INELIGIBLE,
        "apy": MatchStatus.INELIGIBLE,
    },
    "case_12": {
        "sukanya_samriddhi": MatchStatus.ELIGIBLE,
        "pm_kisan": MatchStatus.INELIGIBLE,
    },
    "case_13": {
        "mgnrega": MatchStatus.ELIGIBLE,
        "pm_kisan": MatchStatus.INELIGIBLE,
    },
    "case_15": {
        "nsap_ignoaps": MatchStatus.ELIGIBLE,
        "apy": MatchStatus.INELIGIBLE,
    },
    "case_43": {
        "nsap_ignoaps": MatchStatus.ELIGIBLE,
        "apy": MatchStatus.INELIGIBLE,
    },
    "case_44": {
        "mgnrega": MatchStatus.ELIGIBLE,
        "pmjdy": MatchStatus.ELIGIBLE,
    },
    "case_45": {"sukanya_samriddhi": MatchStatus.ELIGIBLE},
    "case_47": {"nsap_ignoaps": MatchStatus.ELIGIBLE},
    "case_50": {
        "apy": MatchStatus.ELIGIBLE,
        "sukanya_samriddhi": MatchStatus.ELIGIBLE,
    },
}

# Cases expected to raise ValidationError (invalid profile data)
EXPECTED_VALIDATION_ERRORS: set[str] = {"case_46"}

# Cases expected to produce only INSUFFICIENT_DATA (minimal profile)
EXPECTED_ALL_INSUFFICIENT: set[str] = {"case_20"}


def run_engine_for_profile(profile: UserProfile) -> list[dict]:
    """Run all schemes against a profile, return list of result dicts."""
    results = []
    for scheme_data in load_all_schemes():
        scheme = Scheme(**scheme_data)
        rule_results = evaluate_scheme(scheme, profile)
        confidence, status = ConfidenceScorer.score(scheme, rule_results)
        results.append({
            "scheme_id": scheme.scheme_id,
            "scheme_name": scheme.name,
            "status": status.value,
            "confidence": round(confidence, 2),
            "rule_results": [
                {"rule_id": rid, "result": res.value, "explanation": exp}
                for rid, res, exp in rule_results
            ],
        })
    return results


def check_expectations(
    case_id: str,
    scheme_results: list[dict],
) -> list[str]:
    """Return list of mismatch strings, or empty if all expectations met."""
    mismatches = []
    expected = EXPECTED.get(case_id, {})
    status_map = {r["scheme_id"]: r["status"] for r in scheme_results}
    for scheme_id, expected_status in expected.items():
        actual = status_map.get(scheme_id)
        if actual != expected_status.value:
            mismatches.append(
                f"  {scheme_id}: expected {expected_status.value}, got {actual}"
            )
    return mismatches


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    case_files = sorted(FIXTURES_DIR.glob("case_*.json"))
    if not case_files:
        print(f"No case_*.json files found in {FIXTURES_DIR}")
        sys.exit(1)

    report: list[dict] = []
    summary_rows: list[tuple] = []  # (case_id, outcome, note)

    passes = 0
    mismatches_total = 0
    crashes = 0
    validation_errors = 0

    print(f"\n{'='*72}")
    print(f"  Kalam — 50-Case Eligibility Engine Test Run")
    print(f"{'='*72}")
    print(f"  {'Case':<10} {'Outcome':<22} Notes")
    print(f"  {'-'*10} {'-'*22} {'-'*36}")

    for case_file in case_files:
        case_id = case_file.stem  # e.g. "case_01"
        raw = json.loads(case_file.read_text())

        # Attempt profile construction
        try:
            profile = UserProfile(**raw)
        except ValidationError as ve:
            if case_id in EXPECTED_VALIDATION_ERRORS:
                outcome = "VALIDATION_ERROR (expected)"
                note = "age=-5 correctly rejected by Pydantic ge=0"
                passes += 1
                validation_errors += 1
            else:
                outcome = "VALIDATION_ERROR (unexpected)"
                note = str(ve).replace("\n", " ")[:60]
                crashes += 1
            record = {
                "case_id": case_id,
                "outcome": outcome,
                "note": note,
                "profile_raw": raw,
                "scheme_results": [],
                "mismatches": [],
            }
            report.append(record)
            print(f"  {case_id:<10} {outcome:<22} {note[:36]}")
            summary_rows.append((case_id, outcome, note))
            continue
        except Exception as exc:
            outcome = f"PROFILE_BUILD_ERROR"
            note = str(exc)[:60]
            crashes += 1
            record = {
                "case_id": case_id,
                "outcome": outcome,
                "note": note,
                "profile_raw": raw,
                "scheme_results": [],
                "mismatches": [],
            }
            report.append(record)
            print(f"  {case_id:<10} {outcome:<22} {note[:36]}")
            summary_rows.append((case_id, outcome, note))
            continue

        # Run engine
        try:
            scheme_results = run_engine_for_profile(profile)
        except Exception as exc:
            outcome = "ENGINE_CRASH"
            note = str(exc)[:60]
            crashes += 1
            record = {
                "case_id": case_id,
                "outcome": outcome,
                "note": note,
                "profile_raw": raw,
                "scheme_results": [],
                "mismatches": [],
            }
            report.append(record)
            print(f"  {case_id:<10} {outcome:<22} {note[:36]}")
            summary_rows.append((case_id, outcome, note))
            continue

        # Check for all-INSUFFICIENT_DATA cases
        if case_id in EXPECTED_ALL_INSUFFICIENT:
            all_insufficient = all(
                r["status"] == MatchStatus.INSUFFICIENT_DATA.value
                for r in scheme_results
            )
            if all_insufficient:
                outcome = "PASS (all INSUFFICIENT_DATA)"
                note = "Empty profile handled correctly"
                passes += 1
            else:
                non_insuff = [
                    f"{r['scheme_id']}={r['status']}"
                    for r in scheme_results
                    if r["status"] != MatchStatus.INSUFFICIENT_DATA.value
                ]
                outcome = "MISMATCH"
                note = f"Expected all INSUFFICIENT_DATA; got {non_insuff[:3]}"
                mismatches_total += 1
            record = {
                "case_id": case_id,
                "outcome": outcome,
                "note": note,
                "profile_raw": raw,
                "scheme_results": scheme_results,
                "mismatches": [],
            }
            report.append(record)
            print(f"  {case_id:<10} {outcome:<22} {note[:36]}")
            summary_rows.append((case_id, outcome, note))
            continue

        # Check against expected outputs
        mismatches = check_expectations(case_id, scheme_results)
        if mismatches:
            outcome = f"MISMATCH ({len(mismatches)})"
            note = mismatches[0].strip()[:36]
            mismatches_total += 1
        else:
            outcome = "PASS"
            note = ""
            passes += 1

        record = {
            "case_id": case_id,
            "outcome": outcome,
            "note": note,
            "profile_raw": raw,
            "scheme_results": scheme_results,
            "mismatches": mismatches,
        }
        report.append(record)
        print(f"  {case_id:<10} {outcome:<22} {note[:36]}")
        summary_rows.append((case_id, outcome, note))

        # Print mismatch detail
        if mismatches:
            for m in mismatches:
                print(f"    MISMATCH: {m.strip()}")

    # Save report
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str))

    print(f"\n{'='*72}")
    print(f"  Results: {passes}/50 passed | {mismatches_total} mismatches | {crashes} crashes")
    print(f"  Report saved: {REPORT_PATH}")
    print(f"{'='*72}\n")

    # Exit with error code if there are unexpected failures
    if crashes > 0 or mismatches_total > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
