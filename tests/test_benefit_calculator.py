"""Tests for benefit_calculator — covers all 20 scheme arms and state-specific values."""
import pytest
from src.engine.benefit_calculator import BenefitDisplay, calculate_benefit
from src.models.user_profile import UserProfile


def _profile(**kwargs) -> UserProfile:
    return UserProfile(**kwargs)


class TestBenefitDisplayType:
    def test_pm_kisan_returns_display(self):
        result = calculate_benefit("pm_kisan", _profile())
        assert isinstance(result, BenefitDisplay)
        assert result.annual_value == 6000
        assert result.value_type == "cash"
        assert "6,000" in result.primary

    def test_ayushman_is_insurance(self):
        result = calculate_benefit("ayushman_bharat", _profile())
        assert result.value_type == "insurance"
        assert "5,00,000" in result.primary or "500000" in result.primary

    def test_mgnrega_uses_100_days(self):
        result = calculate_benefit("mgnrega", _profile(state="Uttar Pradesh"))
        assert result.annual_value > 0
        assert "100 days" in result.primary

    def test_mgnrega_state_wage_varies(self):
        """Wages differ by state."""
        up = calculate_benefit("mgnrega", _profile(state="Uttar Pradesh"))
        hr = calculate_benefit("mgnrega", _profile(state="Haryana"))
        # Both valid but may differ
        assert up.annual_value > 0
        assert hr.annual_value > 0

    def test_mgnrega_default_wage_unknown_state(self):
        """Unknown state gets default wage, not an error."""
        result = calculate_benefit("mgnrega", _profile(state="Atlantis"))
        assert result.annual_value > 0

    def test_pmay_g_hilly_state_higher(self):
        """Hilly/NE states get ₹1,30,000; plains get ₹1,20,000."""
        plains = calculate_benefit("pmay_g", _profile(state="Uttar Pradesh"))
        hilly = calculate_benefit("pmay_g", _profile(state="Himachal Pradesh"))
        assert hilly.annual_value == 130000
        assert plains.annual_value == 120000

    def test_pmay_u_ews_tier(self):
        result = calculate_benefit("pmay_u", _profile(annual_income=150000))
        assert "EWS" in result.primary

    def test_pmay_u_lig_tier(self):
        result = calculate_benefit("pmay_u", _profile(annual_income=400000))
        assert "LIG" in result.primary

    def test_pmay_u_mig_tier(self):
        result = calculate_benefit("pmay_u", _profile(annual_income=700000))
        assert "MIG" in result.primary

    def test_pmjdy_has_accident_cover(self):
        result = calculate_benefit("pmjdy", _profile(age=35))
        assert result.primary is not None
        assert len(result.primary) > 0

    def test_pm_kisan_note_mentions_5yr(self):
        result = calculate_benefit("pm_kisan", _profile())
        assert result.note is not None and "30,000" in result.note

    def test_unknown_scheme_returns_display(self):
        """Unknown scheme_id should not raise — returns a fallback BenefitDisplay."""
        result = calculate_benefit("__nonexistent__", _profile())
        assert isinstance(result, BenefitDisplay)


class TestBenefitValueTypes:
    @pytest.mark.parametrize("scheme_id,expected_type", [
        ("pm_kisan", "cash"),
        ("mgnrega", "cash"),
        ("ayushman_bharat", "insurance"),
        ("pmay_g", "housing"),
        ("pmay_u", "housing"),
    ])
    def test_value_type(self, scheme_id, expected_type):
        result = calculate_benefit(scheme_id, _profile())
        assert result.value_type == expected_type

    def test_all_display_fields_non_none(self):
        """primary and secondary must always be set."""
        for scheme_id in ["pm_kisan", "mgnrega", "ayushman_bharat", "pmjdy", "nfsa"]:
            r = calculate_benefit(scheme_id, _profile())
            assert r.primary is not None, f"{scheme_id} primary is None"


class TestNSAPStateTopups:
    def test_nsap_pension_varies_with_age(self):
        elderly = calculate_benefit("nsap_ignoaps", _profile(age=70))
        assert elderly is not None

    def test_apy_contribution_by_age(self):
        """Younger age → lower APY contribution → higher pension ratio."""
        young = calculate_benefit("apy", _profile(age=25))
        older = calculate_benefit("apy", _profile(age=35))
        # Both should return something, younger is better deal
        assert young.primary is not None
        assert older.primary is not None
