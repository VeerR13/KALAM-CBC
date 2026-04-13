"""
web_test.py — Full-stack web test for Kalam.

POSTs all 50 case profiles to the local /results route, parses the HTML
response, and compares scheme statuses against the LIVE engine output
(computed fresh by calling _run_engine directly on each profile).

This tests the full stack: form submission → _build_profile → engine → Jinja2
rendering, and verifies the web result matches what the engine returns directly.

Usage:
    # start server first (separate terminal):
    uvicorn web.app:app --port 8000

    python tests/web_test.py [--port 8000] [--base-url http://localhost:8000]
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
PROFILES_DIR = ROOT / "tests" / "fixtures" / "profiles"
RESULTS_DIR = ROOT / "tests" / "results"
RESULTS_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(ROOT))
from src.models.user_profile import UserProfile  # noqa: E402
from web.app import _run_engine  # noqa: E402


def engine_expected(profile_dict: dict) -> list[dict]:
    """
    Run the engine on a profile dict using the SAME form roundtrip the web
    uses (profile_dict → form fields → _build_profile → engine).

    This ensures we compare the web result against what the engine would
    compute given identical information — fields not collectible by the form
    (e.g. previous_scheme_loans) are excluded from both paths.
    """
    from web.app import _build_profile  # noqa: E402
    form = profile_to_form(profile_dict)
    profile = _build_profile(form)
    results = _run_engine(profile)
    return [
        {
            "scheme_id": r.scheme_id,
            "scheme_name": r.scheme_name,
            "status": r.status.value,
            "confidence": r.confidence,
        }
        for r in results
    ]


# ── Profile → form field mapping ───────────────────────────────────────────────
def profile_to_form(profile: dict) -> dict:
    """Convert a profile JSON dict to the flat form fields expected by POST /results."""
    form: dict = {}

    # Direct string/int fields
    for key in [
        "age", "gender", "state", "caste_category", "marital_status",
        "annual_income", "occupation", "family_size", "num_children",
        "num_live_births", "land_ownership", "has_ration_card",
    ]:
        v = profile.get(key)
        if v is not None:
            form[key] = str(v)

    # is_urban: bool → "urban" | "rural"
    if profile.get("is_urban") is not None:
        form["is_urban"] = "urban" if profile["is_urban"] else "rural"

    # land_area_hectares → land_area + land_unit
    if profile.get("land_area_hectares") is not None:
        form["land_area"] = str(profile["land_area_hectares"])
        form["land_unit"] = "hectare"

    # disability_percent: reverse the form map (none→0, 40_79→60, 80_plus→85)
    dp = profile.get("disability_percent")
    if dp is not None:
        if dp == 0:
            form["disability_percent"] = "none"
        elif dp < 80:
            form["disability_percent"] = "40_79"
        else:
            form["disability_percent"] = "80_plus"

    # Boolean fields  (profile_key → form_key)
    bool_map = {
        "has_girl_child_under_10":     "has_girl_child_under_10",
        "is_pregnant_or_lactating":    "is_pregnant_or_lactating",
        "has_existing_enterprise":     "has_enterprise",
        "has_aadhaar":                 "has_aadhaar",
        "has_bank_account":            "has_bank_account",
        "is_aadhaar_linked":           "is_aadhaar_linked",
        "is_govt_employee":            "is_govt_employee",
        "is_income_tax_payer":         "is_income_tax_payer",
        "is_epf_member":               "is_epf_member",
        "has_motorized_vehicle":       "has_motorized_vehicle",
        "has_mechanized_farm_equipment": "has_mechanized_farm_equipment",
        "has_kisan_credit_card":       "has_kisan_credit_card",
        "has_refrigerator":            "has_refrigerator",
        "has_landline":                "has_landline",
        "has_pucca_house":             "has_pucca_house",
        "is_family_head":              "is_family_head",
        "spouse_is_govt_employee":     "spouse_is_govt_employee",
        "has_lpg_connection":          "has_lpg_connection",
        "has_existing_pension":        "has_existing_pension",
    }
    for prof_key, form_key in bool_map.items():
        v = profile.get(prof_key)
        if v is not None:
            form[form_key] = "yes" if v else "no"

    return form


# ── HTML parsing ───────────────────────────────────────────────────────────────
def parse_scheme_cards(html: str) -> list[dict]:
    """
    Extract all scheme cards from the results page — including eligible,
    likely, ambiguous, ineligible (collapsed), and insufficient-data.

    Returns list of {scheme_id, scheme_name, status, confidence}.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_ids: set[str] = set()

    def _extract_card(el, default_status: str = "") -> dict | None:
        status_raw = (el.get("data-status") or default_status).upper()

        # scheme_id: prefer data-scheme-id, fall back to parsing data-href
        scheme_id = el.get("data-scheme-id", "")
        if not scheme_id:
            href = el.get("data-href", "")
            m = re.search(r"/scheme/([^?&#\s]+)", href)
            scheme_id = m.group(1) if m else ""
        # last resort: parse from id="nicard-<scheme_id>"
        if not scheme_id:
            el_id = el.get("id", "")
            if el_id.startswith("nicard-"):
                scheme_id = el_id[len("nicard-"):]

        if not scheme_id or scheme_id in seen_ids:
            return None
        seen_ids.add(scheme_id)

        # scheme_name from .card-name or .needinfo-name
        name_el = el.find(class_="card-name") or el.find(class_="needinfo-name")
        scheme_name = ""
        if name_el:
            for btn in name_el.find_all("button"):
                btn.decompose()
            scheme_name = name_el.get_text(strip=True)

        # confidence from .conf-pct (absent for ineligible/needinfo)
        conf_el = el.find(class_="conf-pct")
        confidence = None
        if conf_el:
            try:
                confidence = float(conf_el.get_text(strip=True).replace("%", ""))
            except ValueError:
                pass

        return {
            "scheme_id": scheme_id,
            "scheme_name": scheme_name,
            "status": status_raw,
            "confidence": confidence,
        }

    # Regular scheme-cards (eligible/likely/ambiguous/ineligible)
    for card in soup.find_all("div", class_="scheme-card"):
        row = _extract_card(card)
        if row:
            results.append(row)

    # Needinfo cards (insufficient_data) — different element class
    for card in soup.find_all("div", class_="needinfo-card"):
        row = _extract_card(card, default_status="insufficient_data")
        if row:
            results.append(row)

    return results


# ── Comparison ─────────────────────────────────────────────────────────────────
def compare(expected: list[dict], actual: list[dict]) -> list[dict]:
    """
    Return list of per-scheme comparison rows.

    Fields: scheme_id, expected_status, actual_status, expected_conf,
            actual_conf, status_match, conf_match, found_in_html.
    """
    actual_by_id = {r["scheme_id"]: r for r in actual}
    rows = []
    for exp in expected:
        sid = exp["scheme_id"]
        act = actual_by_id.get(sid)
        exp_status = exp["status"]
        exp_conf = round(exp["confidence"])
        if act:
            act_status = act["status"]
            act_conf = round(act["confidence"]) if act["confidence"] is not None else None
            rows.append({
                "scheme_id": sid,
                "scheme_name": exp.get("scheme_name", sid),
                "expected_status": exp_status,
                "actual_status": act_status,
                "expected_conf": exp_conf,
                "actual_conf": act_conf,
                "status_match": exp_status == act_status,
                "conf_match": abs((act_conf or 0) - exp_conf) <= 2,
                "found_in_html": True,
            })
        else:
            rows.append({
                "scheme_id": sid,
                "scheme_name": exp.get("scheme_name", sid),
                "expected_status": exp_status,
                "actual_status": None,
                "expected_conf": exp_conf,
                "actual_conf": None,
                "status_match": False,
                "conf_match": False,
                "found_in_html": False,
            })
    return rows


# ── Runner ─────────────────────────────────────────────────────────────────────
def run(base_url: str) -> list[dict]:
    url = base_url.rstrip("/") + "/results"

    # Collect all case profiles
    profile_files = sorted(PROFILES_DIR.glob("case_*.json"))

    report = []
    total_status_mismatches = 0
    total_server_errors = 0
    total_render_errors = 0
    total_missing_cards = 0

    for pf in profile_files:
        case_id = pf.stem
        with open(pf) as f:
            profile = json.load(f)

        form_data = profile_to_form(profile)

        # POST to /results
        try:
            resp = requests.post(url, data=form_data, timeout=30)
            http_status = resp.status_code
            html = resp.text if http_status == 200 else ""
        except requests.RequestException as exc:
            report.append({
                "case_id": case_id,
                "http_status": "CONNECTION_ERROR",
                "error": str(exc),
                "scheme_comparisons": [],
                "summary": {"status_mismatches": 0, "missing_cards": 0,
                             "render_error": True, "server_error": True},
            })
            total_server_errors += 1
            continue

        server_error = http_status >= 500
        render_error = False
        if server_error:
            total_server_errors += 1

        # Check for Jinja2 / Python exception traces in HTML
        if "Traceback" in html or "Internal Server Error" in html or "500" in html[:200]:
            render_error = True
            total_render_errors += 1

        # Parse cards
        actual_cards = parse_scheme_cards(html) if not server_error else []

        # Compare against live engine output
        expected_results = engine_expected(profile)
        comparisons = compare(expected_results, actual_cards)
        n_mismatches = sum(1 for c in comparisons if not c["status_match"])
        n_missing = sum(1 for c in comparisons if not c["found_in_html"])
        total_status_mismatches += n_mismatches
        total_missing_cards += n_missing

        report.append({
            "case_id": case_id,
            "http_status": http_status,
            "render_error": render_error,
            "server_error": server_error,
            "cards_in_html": len(actual_cards),
            "scheme_comparisons": comparisons,
            "summary": {
                "status_mismatches": n_mismatches,
                "missing_cards": n_missing,
                "render_error": render_error,
                "server_error": server_error,
            },
        })

    # Print human-readable summary
    print(f"\n{'='*70}")
    print(f"  KALAM WEB TEST — {len(report)} cases")
    print(f"{'='*70}")
    print(f"  HTTP 500 errors       : {total_server_errors}")
    print(f"  Render errors (trace) : {total_render_errors}")
    print(f"  Status mismatches     : {total_status_mismatches}")
    print(f"  Missing scheme cards  : {total_missing_cards}")

    # Per-case summary table
    print(f"\n  {'CASE':<12} {'HTTP':>5}  {'CARDS':>5}  {'MISMATCHES':>10}  {'MISSING':>7}  STATUS")
    print(f"  {'-'*62}")
    for row in report:
        flags = []
        if row.get("server_error"):
            flags.append("SERVER_ERROR")
        if row.get("render_error"):
            flags.append("RENDER_ERROR")
        s = row["summary"]
        if s["status_mismatches"]:
            flags.append(f"{s['status_mismatches']} MISMATCH(ES)")
        if s["missing_cards"]:
            flags.append(f"{s['missing_cards']} MISSING")
        status_str = ", ".join(flags) if flags else "OK"
        http = row.get("http_status", "ERR")
        cards = row.get("cards_in_html", 0)
        print(f"  {row['case_id']:<12} {str(http):>5}  {cards:>5}  "
              f"{s['status_mismatches']:>10}  {s['missing_cards']:>7}  {status_str}")

    # Print mismatch details
    any_mismatch = False
    for row in report:
        bad = [c for c in row["scheme_comparisons"] if not c["status_match"]]
        if bad:
            if not any_mismatch:
                print(f"\n  {'─'*70}")
                print(f"  MISMATCH DETAILS")
                print(f"  {'─'*70}")
                any_mismatch = True
            print(f"\n  [{row['case_id']}]")
            for c in bad:
                print(f"    {c['scheme_id']:<25}  expected={c['expected_status']:<20} "
                      f"actual={c['actual_status'] or 'MISSING'}")

    verdict = "PASS" if (total_server_errors + total_render_errors + total_status_mismatches + total_missing_cards) == 0 else "FAIL"
    print(f"\n  VERDICT: {verdict}")
    print(f"{'='*70}\n")

    return report


def main():
    parser = argparse.ArgumentParser(description="Kalam full-stack web test")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--base-url", default="")
    args = parser.parse_args()
    base = args.base_url or f"http://localhost:{args.port}"

    # Health check
    try:
        r = requests.get(base + "/", timeout=5)
        if r.status_code != 200:
            print(f"ERROR: server at {base} returned {r.status_code}")
            sys.exit(1)
    except requests.RequestException:
        print(f"ERROR: cannot reach server at {base}")
        print("  Start it with:  uvicorn web.app:app --port 8000")
        sys.exit(1)

    t0 = time.time()
    report = run(base)
    elapsed = time.time() - t0

    out = RESULTS_DIR / "web_test_report.json"
    with open(out, "w") as f:
        json.dump({"elapsed_s": round(elapsed, 2), "cases": report}, f, indent=2)
    print(f"  Full report saved to {out.relative_to(ROOT)}")

    # Exit non-zero if any failures
    any_fail = any(
        r["summary"]["server_error"] or r["summary"]["render_error"] or
        r["summary"]["status_mismatches"] or r["summary"]["missing_cards"]
        for r in report
    )
    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
