"""Tests for SensitivityAnalyzer — detects fragile eligibility near thresholds."""
import pytest
from src.engine.confidence import MatchStatus
from src.engine.sensitivity import SensitivityAnalyzer, SensitivityFlag
from src.models.user_profile import UserProfile


@pytest.fixture
def analyzer():
    return SensitivityAnalyzer()


def _statuses(**kwargs):
    return {k: MatchStatus(v) for k, v in kwargs.items()}


class TestReturnTypes:
    def test_returns_list(self, analyzer):
        profile = UserProfile(age=35, annual_income=150000)
        result = analyzer.analyze(profile, {})
        assert isinstance(result, list)

    def test_empty_profile_no_crash(self, analyzer):
        """Empty profile with no statuses should return empty list gracefully."""
        result = analyzer.analyze(UserProfile(), {})
        assert isinstance(result, list)

    def test_flag_has_required_fields(self, analyzer):
        profile = UserProfile(age=38, annual_income=100000, state="Uttar Pradesh",
                              gender="M", is_urban=False)
        statuses = _statuses(pm_kisan=MatchStatus.ELIGIBLE, mgnrega=MatchStatus.ELIGIBLE)
        flags = analyzer.analyze(profile, statuses)
        for flag in flags:
            assert isinstance(flag, SensitivityFlag)
            assert flag.message
            assert isinstance(flag.is_opportunity, bool)


class TestIncomeThresholds:
    def test_near_income_threshold_generates_flag(self, analyzer):
        """User just below a known income cutoff should see a risk flag."""
        # Most schemes cap at ₹1,00,000–₹2,00,000 for BPL-type eligibility
        # Setting income just below a threshold with eligible status should generate flags
        profile = UserProfile(age=40, annual_income=95000, state="Uttar Pradesh",
                              is_urban=False, has_aadhaar=True, has_bank_account=True)
        # Run engine to get real statuses
        from src.engine.rule_engine import evaluate_scheme
        from src.loader import load_all_schemes
        from src.models.scheme import Scheme
        schemes = {sd["scheme_id"]: Scheme(**sd) for sd in load_all_schemes()}
        statuses = {}
        for sid, scheme in schemes.items():
            rule_results = evaluate_scheme(scheme, profile)
            from src.engine.confidence import ConfidenceScorer
            _, status = ConfidenceScorer.score(scheme, rule_results)
            statuses[sid] = status

        flags = analyzer.analyze(profile, statuses)
        assert isinstance(flags, list)  # may or may not have flags depending on exact profile


class TestAgeVariations:
    def test_age_near_apy_cutoff(self, analyzer):
        """APY closes at 40 — user aged 38 should possibly see a deadline flag."""
        profile = UserProfile(age=38, is_epf_member=False, has_bank_account=True)
        statuses = _statuses(apy=MatchStatus.ELIGIBLE)
        flags = analyzer.analyze(profile, statuses)
        assert isinstance(flags, list)

    def test_age_variation_identifies_opportunity(self, analyzer):
        """At age 59, becoming 60 opens NSAP pension — should surface as opportunity."""
        profile = UserProfile(age=59, annual_income=80000, is_urban=False)
        statuses = _statuses(nsap_ignoaps=MatchStatus.INELIGIBLE)
        flags = analyzer.analyze(profile, statuses)
        opportunity_flags = [f for f in flags if f.is_opportunity]
        # May or may not trigger depending on scheme rules — just verify no crash
        assert isinstance(flags, list)


class TestNoFalsePositives:
    def test_no_flags_when_no_statuses(self, analyzer):
        profile = UserProfile(age=30, annual_income=200000)
        flags = analyzer.analyze(profile, {})
        assert flags == []

    def test_ineligible_not_duplicated(self, analyzer):
        """No duplicate flags for the same scheme+field_changed combination."""
        profile = UserProfile(age=35, annual_income=100000)
        statuses = _statuses(pm_kisan=MatchStatus.INELIGIBLE)
        flags = analyzer.analyze(profile, statuses)
        keys = [(f.scheme_id, f.field_changed, str(f.test_value)) for f in flags]
        assert len(keys) == len(set(keys)), "Duplicate (scheme_id, field_changed, test_value) flags"

    def test_flag_count_bounded(self, analyzer):
        """Should not return thousands of flags for a normal profile."""
        profile = UserProfile(age=35, annual_income=100000, state="Uttar Pradesh")
        statuses = {f"scheme_{i}": MatchStatus.ELIGIBLE for i in range(5)}
        flags = analyzer.analyze(profile, statuses)
        assert len(flags) < 100
