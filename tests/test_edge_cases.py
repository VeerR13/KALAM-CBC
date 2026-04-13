"""Edge case integration tests — 10 adversarial profiles through the full engine pipeline."""
import json
from pathlib import Path
import pytest
from src.models.user_profile import UserProfile
from src.models.scheme import Scheme
from src.engine.rule_engine import evaluate_scheme
from src.engine.confidence import ConfidenceScorer, MatchStatus
from src.loader import load_scheme

PROFILES_DIR = Path(__file__).parent / "fixtures" / "profiles"
EXPECTED_DIR = Path(__file__).parent / "fixtures" / "expected_results"


def run_engine(profile: UserProfile, scheme_id: str) -> tuple[float, MatchStatus]:
    """Run full pipeline: load scheme → evaluate rules → score confidence."""
    scheme_data = load_scheme(scheme_id)
    scheme = Scheme(**scheme_data)
    rule_results = evaluate_scheme(scheme, profile)
    return ConfidenceScorer.score(scheme, rule_results)


def load_profile(name: str) -> UserProfile:
    data = json.loads((PROFILES_DIR / f"{name}.json").read_text())
    return UserProfile(**data)


# ── Edge Case 01: Remarried Widow ────────────────────────────────────────────

def test_edge_01_ignwps_ineligible_remarried():
    profile = load_profile("edge_01_remarried_widow")
    _, status = run_engine(profile, "nsap_ignwps")
    assert status == MatchStatus.INELIGIBLE  # married, not widowed


def test_edge_01_ignoaps_ineligible_too_young():
    profile = load_profile("edge_01_remarried_widow")
    _, status = run_engine(profile, "nsap_ignoaps")
    assert status == MatchStatus.INELIGIBLE  # age=52 < 60


def test_edge_01_mgnrega_eligible():
    profile = load_profile("edge_01_remarried_widow")
    _, status = run_engine(profile, "mgnrega")
    assert status == MatchStatus.ELIGIBLE


# ── Edge Case 02: Leased Farmer ──────────────────────────────────────────────

def test_edge_02_pm_kisan_ambiguous_leased_land():
    profile = load_profile("edge_02_leased_farmer")
    _, status = run_engine(profile, "pm_kisan")
    assert status == MatchStatus.AMBIGUOUS  # land_ownership=leases → AMBIGUOUS


def test_edge_02_mgnrega_eligible():
    profile = load_profile("edge_02_leased_farmer")
    _, status = run_engine(profile, "mgnrega")
    assert status == MatchStatus.ELIGIBLE


# ── Edge Case 03: No Bank Account ────────────────────────────────────────────

def test_edge_03_pmjdy_eligible():
    """PMJDY should be eligible — designed for the unbanked."""
    profile = load_profile("edge_03_no_bank_account")
    _, status = run_engine(profile, "pmjdy")
    assert status == MatchStatus.ELIGIBLE


def test_edge_03_pm_kisan_ineligible_no_aadhaar_link():
    profile = load_profile("edge_03_no_bank_account")
    _, status = run_engine(profile, "pm_kisan")
    # is_aadhaar_linked=false → mandatory FAIL
    assert status == MatchStatus.INELIGIBLE


# ── Edge Case 04: Urban Vendor ────────────────────────────────────────────────

def test_edge_04_svanidhi_eligible():
    profile = load_profile("edge_04_urban_vendor_overlap")
    _, status = run_engine(profile, "pm_svanidhi")
    assert status == MatchStatus.ELIGIBLE


def test_edge_04_mgnrega_ineligible_urban():
    profile = load_profile("edge_04_urban_vendor_overlap")
    _, status = run_engine(profile, "mgnrega")
    assert status == MatchStatus.INELIGIBLE


def test_edge_04_pmegp_ineligible_existing_enterprise():
    profile = load_profile("edge_04_urban_vendor_overlap")
    _, status = run_engine(profile, "pmegp")
    assert status == MatchStatus.INELIGIBLE


# ── Edge Case 05: Transgender BPL ────────────────────────────────────────────

def test_edge_05_ujjwala_ambiguous_transgender():
    profile = load_profile("edge_05_transgender_bpl")
    _, status = run_engine(profile, "ujjwala")
    # gender=Transgender is in ambiguous_values for female-only schemes
    assert status == MatchStatus.AMBIGUOUS


def test_edge_05_ayushman_eligible():
    profile = load_profile("edge_05_transgender_bpl")
    _, status = run_engine(profile, "ayushman_bharat")
    assert status in (MatchStatus.ELIGIBLE, MatchStatus.LIKELY_ELIGIBLE)


# ── Edge Case 06: Govt Employee Spouse ───────────────────────────────────────

def test_edge_06_pm_kisan_eligible_because_she_is_not_govt_employee():
    """PM-KISAN exclusion applies to the applicant, not the spouse."""
    profile = load_profile("edge_06_govt_employee_spouse_farmer")
    _, status = run_engine(profile, "pm_kisan")
    assert status in (MatchStatus.ELIGIBLE, MatchStatus.LIKELY_ELIGIBLE)


# ── Edge Case 07: Just Turned 18 ─────────────────────────────────────────────

def test_edge_07_mgnrega_eligible_at_exactly_18():
    profile = load_profile("edge_07_just_turned_18")
    _, status = run_engine(profile, "mgnrega")
    assert status == MatchStatus.ELIGIBLE


def test_edge_07_pmjdy_eligible_no_bank():
    profile = load_profile("edge_07_just_turned_18")
    _, status = run_engine(profile, "pmjdy")
    assert status == MatchStatus.ELIGIBLE


# ── Edge Case 08: Migrant Worker ─────────────────────────────────────────────

def test_edge_08_mgnrega_ineligible_urban():
    profile = load_profile("edge_08_migrant_worker")
    _, status = run_engine(profile, "mgnrega")
    assert status == MatchStatus.INELIGIBLE


def test_edge_08_pm_sym_eligible():
    profile = load_profile("edge_08_migrant_worker")
    _, status = run_engine(profile, "pm_sym")
    assert status in (MatchStatus.ELIGIBLE, MatchStatus.LIKELY_ELIGIBLE)


# ── Edge Case 09: Income Crossed Tax Threshold ───────────────────────────────

def test_edge_09_pm_kisan_ineligible_income_tax_payer():
    profile = load_profile("edge_09_income_crossed_tax")
    _, status = run_engine(profile, "pm_kisan")
    assert status == MatchStatus.INELIGIBLE


def test_edge_09_nfsa_ineligible_income_tax_payer():
    profile = load_profile("edge_09_income_crossed_tax")
    _, status = run_engine(profile, "nfsa")
    assert status == MatchStatus.INELIGIBLE


def test_edge_09_mgnrega_eligible():
    """MGNREGA has no income exclusion — even tax payers can apply."""
    profile = load_profile("edge_09_income_crossed_tax")
    _, status = run_engine(profile, "mgnrega")
    assert status == MatchStatus.ELIGIBLE


# ── Edge Case 10: Disabled, No Aadhaar ───────────────────────────────────────

def test_edge_10_igndps_ineligible_no_aadhaar():
    profile = load_profile("edge_10_disabled_no_aadhaar")
    _, status = run_engine(profile, "nsap_igndps")
    assert status == MatchStatus.INELIGIBLE


def test_edge_10_pmjdy_ineligible_no_aadhaar():
    profile = load_profile("edge_10_disabled_no_aadhaar")
    _, status = run_engine(profile, "pmjdy")
    assert status == MatchStatus.INELIGIBLE
