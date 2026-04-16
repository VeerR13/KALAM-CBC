"""Tests for PathOptimizer — step ordering, totals, and OptimalPath structure."""
import pytest
from src.engine.interaction_detector import Interaction
from src.engine.path_optimizer import OptimalPath, PathOptimizer, PathStep
from src.models.user_profile import UserProfile


@pytest.fixture
def optimizer():
    return PathOptimizer(scheme_name_map={
        "pmjdy": "PM Jan Dhan Yojana",
        "nfsa": "National Food Security Act",
        "ayushman_bharat": "Ayushman Bharat PM-JAY",
        "pm_kisan": "PM-KISAN",
        "mgnrega": "MGNREGA",
        "pm_mudra": "PM MUDRA",
        "pmegp": "PMEGP",
    })


@pytest.fixture
def profile():
    return UserProfile(age=35, annual_income=100000, state="Uttar Pradesh",
                       family_size=4, is_urban=False)


class TestReturnType:
    def test_returns_optimal_path(self, optimizer, profile):
        result = optimizer.recommend(profile, [], [])
        assert isinstance(result, OptimalPath)

    def test_empty_eligible_no_steps(self, optimizer, profile):
        result = optimizer.recommend(profile, [], [])
        assert result.steps == []

    def test_steps_are_path_steps(self, optimizer, profile):
        result = optimizer.recommend(profile, ["pm_kisan", "mgnrega"], [])
        for step in result.steps:
            assert isinstance(step, PathStep)


class TestStepOrdering:
    def test_pmjdy_comes_before_pm_kisan(self, optimizer, profile):
        """PMJDY must appear before PM-KISAN (it's a prerequisite enabler)."""
        result = optimizer.recommend(profile, ["pm_kisan", "pmjdy"], [])
        ids = [s.scheme_id for s in result.steps]
        assert ids.index("pmjdy") < ids.index("pm_kisan")

    def test_nfsa_comes_before_ayushman(self, optimizer, profile):
        """Ration card (NFSA) should precede Ayushman Bharat."""
        result = optimizer.recommend(profile, ["ayushman_bharat", "nfsa"], [])
        ids = [s.scheme_id for s in result.steps]
        if "nfsa" in ids and "ayushman_bharat" in ids:
            assert ids.index("nfsa") < ids.index("ayushman_bharat")

    def test_all_eligible_ids_in_steps(self, optimizer, profile):
        eligible = ["pm_kisan", "mgnrega", "pmjdy"]
        result = optimizer.recommend(profile, eligible, [])
        step_ids = {s.scheme_id for s in result.steps}
        assert set(eligible) == step_ids

    def test_unknown_scheme_still_included(self, optimizer, profile):
        """Schemes not in _STEP_META or _PRIORITY_ORDER still appear as steps."""
        result = optimizer.recommend(profile, ["pm_kisan", "__custom_scheme__"], [])
        step_ids = {s.scheme_id for s in result.steps}
        assert "__custom_scheme__" in step_ids


class TestStepFields:
    def test_step_has_scheme_name(self, optimizer, profile):
        result = optimizer.recommend(profile, ["pm_kisan"], [])
        assert result.steps[0].scheme_name == "PM-KISAN"

    def test_step_name_fallback_for_unknown(self, optimizer, profile):
        """For unknown scheme IDs, name is auto-generated from ID."""
        optimizer2 = PathOptimizer(scheme_name_map={})
        result = optimizer2.recommend(profile, ["some_scheme"], [])
        assert result.steps[0].scheme_name  # non-empty

    def test_step_has_where_to_go(self, optimizer, profile):
        result = optimizer.recommend(profile, ["pmjdy"], [])
        assert result.steps[0].where_to_go


class TestBenefitTotals:
    def test_total_cash_positive_for_cash_schemes(self, optimizer, profile):
        result = optimizer.recommend(profile, ["pm_kisan", "mgnrega"], [])
        assert result.total_annual_cash > 0

    def test_insurance_counted_for_ayushman(self, optimizer, profile):
        result = optimizer.recommend(profile, ["ayushman_bharat"], [])
        assert result.total_insurance_cover > 0

    def test_summary_lines_populated(self, optimizer, profile):
        result = optimizer.recommend(profile, ["pm_kisan"], [])
        assert len(result.summary_lines) >= 1
        assert any("₹" in line for line in result.summary_lines)

    def test_totals_zero_for_unknown_schemes(self, optimizer, profile):
        """Unknown scheme IDs don't crash — totals may be 0."""
        result = optimizer.recommend(profile, ["__nonexistent__"], [])
        assert result.total_annual_cash >= 0

    def test_interactions_passed_through(self, optimizer, profile):
        """Interactions list is stored as-is on OptimalPath."""
        fake_ix = Interaction(
            trigger_scheme="pmegp", affected_schemes=["pm_vishwakarma"],
            interaction_type="mutual_exclusion_5yr", title="Test",
            description="Test", severity="choice",
        )
        result = optimizer.recommend(profile, ["pmegp"], [fake_ix])
        assert result.interactions == [fake_ix]
