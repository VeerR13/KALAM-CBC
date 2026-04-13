"""
fuzz_test.py — Stress-tests Kalam with 100 randomly generated profiles.

Tests both the engine (direct Python call) and the web server (POST /results).
Target: ZERO crashes. The system must gracefully handle any garbage input.

Usage:
    # start server first (separate terminal):
    uvicorn web.app:app --port 8000

    python tests/fuzz_test.py [--port 8000] [--seed 42] [--count 100]
"""

import argparse
import json
import random
import sys
import time
import traceback
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
RESULTS_DIR = ROOT / "tests" / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# Add project root to sys.path for imports
sys.path.insert(0, str(ROOT))

from src.models.user_profile import UserProfile  # noqa: E402
from web.app import _run_engine  # noqa: E402

# ── Valid enumerations ─────────────────────────────────────────────────────────
VALID_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
    "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Delhi", "Jammu and Kashmir", "Ladakh",
]
VALID_GENDERS = ["M", "F", "Transgender"]
VALID_CASTES = ["General", "OBC", "SC", "ST"]
VALID_OCCUPATIONS = [
    "farmer", "agricultural_labourer", "daily_wage_labourer", "construction_worker",
    "street_vendor", "domestic_worker", "artisan", "weaver", "carpenter",
    "blacksmith", "potter", "tailor", "cobbler", "fisherman", "shepherd",
    "self_employed", "small_trader", "driver", "unemployed", "student",
]
VALID_MARITAL = ["unmarried", "married", "widowed", "divorced", "separated"]
VALID_LAND = ["owns", "leases", "sharecrop", "none"]
VALID_RATION = ["AAY", "PHH", "none", "unknown"]
VALID_SCHEME_IDS = [
    "pm_kisan", "mgnrega", "ayushman_bharat", "pmay_g", "pmay_u", "pmjdy",
    "ujjwala", "nsap_ignoaps", "nsap_ignwps", "nsap_igndps", "apy", "pm_sym",
    "pm_svanidhi", "pm_mudra", "pmegp", "stand_up_india", "sukanya_samriddhi",
    "pmmvy", "nfsa", "pm_vishwakarma",
]

# ── Profile generators ─────────────────────────────────────────────────────────
def _rand_bool(rng: random.Random) -> bool | None:
    return rng.choice([True, False, None, None])


def _rand_bool_trio(rng: random.Random, weight_none: float = 0.3) -> bool | None:
    r = rng.random()
    if r < weight_none:
        return None
    return rng.random() > 0.5


def generate_profile(rng: random.Random, profile_type: str = "mixed") -> UserProfile:
    """Generate a random UserProfile.

    profile_type:
      mixed      — random mix of valid/invalid values
      all_true   — all booleans True
      all_false  — all booleans False
      all_none   — all booleans/fields None
      extreme    — extreme numeric values + garbage strings
    """
    kwargs: dict = {}

    if profile_type == "all_none":
        return UserProfile()

    if profile_type == "all_true":
        kwargs.update(
            age=rng.randint(18, 80),
            is_urban=True,
            has_aadhaar=True, has_bank_account=True, is_aadhaar_linked=True,
            is_govt_employee=True, is_income_tax_payer=True, is_epf_member=True,
            has_pucca_house=True, has_motorized_vehicle=True,
            has_mechanized_farm_equipment=True, has_kisan_credit_card=True,
            has_refrigerator=True, has_landline=True,
            has_existing_enterprise=True, is_family_head=True,
            spouse_is_govt_employee=True, has_lpg_connection=True,
            has_existing_pension=True, has_girl_child_under_10=True,
            is_pregnant_or_lactating=True,
        )
        return UserProfile(**kwargs)

    if profile_type == "all_false":
        kwargs.update(
            age=rng.randint(18, 80),
            is_urban=False,
            has_aadhaar=False, has_bank_account=False, is_aadhaar_linked=False,
            is_govt_employee=False, is_income_tax_payer=False, is_epf_member=False,
            has_pucca_house=False, has_motorized_vehicle=False,
            has_mechanized_farm_equipment=False, has_kisan_credit_card=False,
            has_refrigerator=False, has_landline=False,
            has_existing_enterprise=False, is_family_head=False,
            spouse_is_govt_employee=False, has_lpg_connection=False,
            has_existing_pension=False, has_girl_child_under_10=False,
            is_pregnant_or_lactating=False,
        )
        return UserProfile(**kwargs)

    # mixed / extreme
    age_choices = (
        [None, -5, 0, 1, 150, 200, -100, rng.randint(1, 200)]
        if profile_type == "extreme"
        else [None, rng.randint(0, 200), rng.randint(5, 90)]
    )
    kwargs["age"] = rng.choice(age_choices)

    income_choices = (
        [None, 0, -1, 10_00_00_000, rng.randint(0, 10_00_00_000)]
        if profile_type == "extreme"
        else [None, 0, rng.randint(0, 10_00_00_000)]
    )
    kwargs["annual_income"] = rng.choice(income_choices)

    state_pool = VALID_STATES + ["", "XYZ_INVALID", "Wakanda", None, "123", "   "]
    kwargs["state"] = rng.choice(state_pool if profile_type == "extreme" else VALID_STATES + [None, None])

    occ_pool = (
        VALID_OCCUPATIONS + ["", "garbage_job", None, "xyz!@#", "123456"]
        if profile_type == "extreme"
        else VALID_OCCUPATIONS + [None, None]
    )
    kwargs["occupation"] = rng.choice(occ_pool)

    kwargs["gender"] = rng.choice(VALID_GENDERS + ([None, "", "XYZ"] if profile_type == "extreme" else [None]))
    kwargs["caste_category"] = rng.choice(VALID_CASTES + [None])
    kwargs["marital_status"] = rng.choice(VALID_MARITAL + [None])
    kwargs["land_ownership"] = rng.choice(VALID_LAND + [None])
    kwargs["has_ration_card"] = rng.choice(VALID_RATION + [None])
    kwargs["is_urban"] = rng.choice([True, False, None])

    family_size_pool = ([-1, 0, None, rng.randint(1, 30), 100] if profile_type == "extreme"
                        else [None, rng.randint(1, 15)])
    kwargs["family_size"] = rng.choice(family_size_pool)

    # Numeric optional fields
    dp_pool = ([-10, 0, 39, 40, 79, 80, 100, 120, None]
               if profile_type == "extreme"
               else [0, rng.randint(0, 100), None])
    kwargs["disability_percent"] = rng.choice(dp_pool)

    if kwargs.get("land_ownership") and kwargs["land_ownership"] != "none":
        la_pool = ([0, -1.0, 0.01, 50.0, 1000.0] if profile_type == "extreme"
                   else [0.1, rng.uniform(0.01, 10.0), None])
        kwargs["land_area_hectares"] = rng.choice(la_pool)

    kwargs["num_children"] = rng.choice([None, 0, rng.randint(0, 10)])
    kwargs["num_live_births"] = rng.choice([None, 0, rng.randint(0, 10)])

    # Previous scheme loans — mix of valid, garbage, empty
    loans_pool = [
        [],
        rng.sample(VALID_SCHEME_IDS, k=rng.randint(1, 3)),
        ["garbage_scheme_id", "FAKE123"],
        rng.sample(VALID_SCHEME_IDS, k=2) + ["garbage"],
        None,
    ]
    kwargs["previous_scheme_loans"] = rng.choice(loans_pool)

    # Booleans
    bool_fields = [
        "has_aadhaar", "has_bank_account", "is_aadhaar_linked", "is_govt_employee",
        "is_income_tax_payer", "is_epf_member", "has_motorized_vehicle",
        "has_mechanized_farm_equipment", "has_kisan_credit_card", "has_refrigerator",
        "has_landline", "has_pucca_house", "has_existing_enterprise", "is_family_head",
        "spouse_is_govt_employee", "has_lpg_connection", "has_existing_pension",
        "has_girl_child_under_10", "is_pregnant_or_lactating",
    ]
    none_weight = 0.5 if profile_type == "extreme" else 0.25
    for field in bool_fields:
        kwargs[field] = _rand_bool_trio(rng, weight_none=none_weight)

    # Clean up None for pydantic (pass only non-None or allow None)
    # Also drop keys with invalid-type values (fuzz may produce garbage strings
    # for Literal fields — those go through the form which ignores them anyway)
    clean = {k: v for k, v in kwargs.items() if v is not None}
    # Clamp validated numeric ranges
    if "age" in clean:
        clean["age"] = max(0, min(150, int(clean["age"]))) if clean["age"] is not None else None
    if "annual_income" in clean and clean["annual_income"] is not None:
        clean["annual_income"] = max(0, clean["annual_income"])
    if "family_size" in clean and clean["family_size"] is not None:
        clean["family_size"] = max(1, clean["family_size"])
    if "disability_percent" in clean and clean["disability_percent"] is not None:
        clean["disability_percent"] = max(0, min(100, clean["disability_percent"]))
    # Validate gender
    if clean.get("gender") not in ("M", "F", "Transgender", None):
        del clean["gender"]
    try:
        return UserProfile(**clean)
    except Exception:
        # Extreme-mode garbage — fall back to an empty profile
        return UserProfile()


# ── Form field builder for web tests ──────────────────────────────────────────
def profile_to_form(profile: UserProfile) -> dict:
    """Convert a UserProfile to web form fields for POST /results."""
    form: dict = {}
    if profile.age is not None:
        form["age"] = str(profile.age)
    if profile.gender:
        form["gender"] = profile.gender
    if profile.state:
        form["state"] = profile.state
    if profile.is_urban is not None:
        form["is_urban"] = "urban" if profile.is_urban else "rural"
    if profile.caste_category:
        form["caste_category"] = profile.caste_category
    if profile.marital_status:
        form["marital_status"] = profile.marital_status
    if profile.annual_income is not None:
        form["annual_income"] = str(profile.annual_income)
    if profile.occupation:
        form["occupation"] = profile.occupation
    if profile.family_size is not None:
        form["family_size"] = str(profile.family_size)
    if profile.num_children is not None:
        form["num_children"] = str(profile.num_children)
    if profile.num_live_births is not None:
        form["num_live_births"] = str(profile.num_live_births)
    if profile.land_ownership:
        form["land_ownership"] = profile.land_ownership
    if profile.land_area_hectares is not None:
        form["land_area"] = str(profile.land_area_hectares)
        form["land_unit"] = "hectare"
    if profile.has_ration_card:
        form["has_ration_card"] = profile.has_ration_card
    if profile.disability_percent is not None:
        dp = profile.disability_percent
        form["disability_percent"] = "none" if dp == 0 else ("80_plus" if dp >= 80 else "40_79")

    bool_map = {
        "has_aadhaar": "has_aadhaar",
        "has_bank_account": "has_bank_account",
        "is_aadhaar_linked": "is_aadhaar_linked",
        "is_govt_employee": "is_govt_employee",
        "is_income_tax_payer": "is_income_tax_payer",
        "is_epf_member": "is_epf_member",
        "has_motorized_vehicle": "has_motorized_vehicle",
        "has_mechanized_farm_equipment": "has_mechanized_farm_equipment",
        "has_kisan_credit_card": "has_kisan_credit_card",
        "has_refrigerator": "has_refrigerator",
        "has_landline": "has_landline",
        "has_pucca_house": "has_pucca_house",
        "has_existing_enterprise": "has_enterprise",
        "is_family_head": "is_family_head",
        "spouse_is_govt_employee": "spouse_is_govt_employee",
        "has_lpg_connection": "has_lpg_connection",
        "has_existing_pension": "has_existing_pension",
        "has_girl_child_under_10": "has_girl_child_under_10",
        "is_pregnant_or_lactating": "is_pregnant_or_lactating",
    }
    for attr, form_key in bool_map.items():
        v = getattr(profile, attr, None)
        if v is not None:
            form[form_key] = "yes" if v else "no"

    return form


# ── Validation helpers ─────────────────────────────────────────────────────────
def validate_engine_results(results: list, valid_ids: set) -> list[str]:
    """Return list of validation failure messages."""
    failures = []
    for r in results:
        sid = getattr(r, "scheme_id", "?")
        conf = getattr(r, "confidence", None)
        status = getattr(r, "status", None)

        if conf is not None:
            if conf < 0:
                failures.append(f"{sid}: confidence={conf} < 0")
            if conf > 100:
                failures.append(f"{sid}: confidence={conf} > 100")

        if status is not None:
            sv = getattr(status, "value", str(status))
            if sv == "":
                failures.append(f"{sid}: status is empty string")

        if sid not in valid_ids:
            failures.append(f"unknown scheme_id in result: {sid!r}")

    return failures


# ── Runner ─────────────────────────────────────────────────────────────────────
def run(base_url: str, count: int, seed: int) -> dict:
    rng = random.Random(seed)
    url = base_url.rstrip("/") + "/results"

    valid_ids = set(VALID_SCHEME_IDS)

    # Profile type distribution
    profile_types = (
        ["all_none"] * 3
        + ["all_true"] * 5
        + ["all_false"] * 5
        + ["extreme"] * 12
        + ["mixed"] * (count - 25)
    )
    rng.shuffle(profile_types)
    profile_types = profile_types[:count]

    results = []
    engine_crashes = 0
    engine_invalid = 0
    web_crashes = 0
    web_errors = 0

    print(f"\nRunning {count} fuzz profiles (seed={seed})...")
    print(f"{'#':>4}  {'TYPE':<12}  {'ENGINE':>8}  {'WEB':>5}  ISSUES")
    print(f"{'─'*60}")

    for i, ptype in enumerate(profile_types, 1):
        profile = generate_profile(rng, ptype)
        row = {
            "index": i,
            "profile_type": ptype,
            "profile_snippet": {
                "age": profile.age,
                "gender": profile.gender,
                "state": profile.state,
                "annual_income": profile.annual_income,
                "occupation": profile.occupation,
            },
            "engine_ok": False,
            "engine_result_count": 0,
            "engine_error": None,
            "engine_validation_failures": [],
            "web_http_status": None,
            "web_ok": False,
            "web_error": None,
        }

        # ── Engine test ────────────────────────────────────────────────────
        try:
            engine_results = _run_engine(profile)
            row["engine_ok"] = True
            row["engine_result_count"] = len(engine_results)
            vfails = validate_engine_results(engine_results, valid_ids)
            row["engine_validation_failures"] = vfails
            if vfails:
                engine_invalid += 1
        except Exception as exc:
            row["engine_error"] = traceback.format_exc()
            engine_crashes += 1

        # ── Web test ───────────────────────────────────────────────────────
        try:
            form = profile_to_form(profile)
            resp = requests.post(url, data=form, timeout=20)
            row["web_http_status"] = resp.status_code
            row["web_ok"] = resp.status_code == 200
            if resp.status_code >= 500:
                web_crashes += 1
                row["web_error"] = f"HTTP {resp.status_code}"
                # Capture brief error context
                if "Traceback" in resp.text:
                    lines = resp.text.split("\n")
                    for idx, ln in enumerate(lines):
                        if "Traceback" in ln:
                            row["web_error"] = "\n".join(lines[idx:idx+6])
                            break
            elif resp.status_code >= 400:
                web_errors += 1
                row["web_error"] = f"HTTP {resp.status_code}"
        except requests.RequestException as exc:
            row["web_error"] = str(exc)
            web_crashes += 1

        issues = []
        if not row["engine_ok"]:
            issues.append("ENGINE_CRASH")
        if row["engine_validation_failures"]:
            issues.append(f"INVALID({len(row['engine_validation_failures'])})")
        if row["web_http_status"] and row["web_http_status"] >= 500:
            issues.append(f"WEB_{row['web_http_status']}")
        issue_str = ", ".join(issues) if issues else "OK"

        # Progress line every 10 or on failure
        if i % 10 == 0 or issues:
            print(f"{i:>4}  {ptype:<12}  {'OK' if row['engine_ok'] else 'CRASH':>8}  "
                  f"{str(row['web_http_status'] or '?'):>5}  {issue_str}")

        results.append(row)

    # Summary
    passed = sum(1 for r in results
                 if r["engine_ok"] and not r["engine_validation_failures"] and r["web_ok"])

    summary = {
        "seed": seed,
        "count": count,
        "engine_crashes": engine_crashes,
        "engine_validation_failures": engine_invalid,
        "web_500_errors": web_crashes,
        "web_4xx_errors": web_errors,
        "fully_passed": passed,
        "verdict": "PASS" if (engine_crashes + engine_invalid + web_crashes) == 0 else "FAIL",
    }

    print(f"\n{'='*60}")
    print(f"  FUZZ RESULTS (seed={seed})")
    print(f"{'='*60}")
    print(f"  Profiles tested       : {count}")
    print(f"  Engine crashes        : {engine_crashes}")
    print(f"  Engine invalid output : {engine_invalid}")
    print(f"  Web 5xx errors        : {web_crashes}")
    print(f"  Web 4xx errors        : {web_errors}")
    print(f"  Fully passed          : {passed}/{count}")
    print(f"  VERDICT               : {summary['verdict']}")
    print(f"{'='*60}\n")

    return {"summary": summary, "results": results}


def main():
    parser = argparse.ArgumentParser(description="Kalam fuzz test")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=100)
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
    report = run(base, args.count, args.seed)
    elapsed = time.time() - t0
    report["elapsed_s"] = round(elapsed, 2)

    out = RESULTS_DIR / "fuzz_report.json"
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  Full report saved to {out.relative_to(ROOT)}")

    sys.exit(0 if report["summary"]["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
