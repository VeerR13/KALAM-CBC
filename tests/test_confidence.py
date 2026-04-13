"""Tests for confidence scorer — one test per threshold boundary."""
from src.models.scheme import Rule, RuleCondition, RuleResult, Scheme, RequiredDocument
from src.engine.confidence import ConfidenceScorer, MatchStatus


def _scheme(rules_spec: list[dict]) -> Scheme:
    rules = [
        Rule(rule_id=f"R{i:02d}", parameter=f"p{i}", description=f"rule {i}",
             condition=RuleCondition(type="boolean_check", field="has_bank_account", equals=True),
             is_mandatory=spec["mandatory"], weight=spec["weight"])
        for i, spec in enumerate(rules_spec)
    ]
    return Scheme(scheme_id="test", name="Test", full_name="Test Scheme",
                  target_description="test", ministry="test", data_source="test",
                  data_freshness="test", rules=rules, required_documents=[],
                  benefit_summary="test")


def test_all_pass_eligible():
    scheme = _scheme([{"mandatory": True, "weight": 50}, {"mandatory": True, "weight": 50}])
    results = [("R00", RuleResult.PASS, "ok"), ("R01", RuleResult.PASS, "ok")]
    score, status = ConfidenceScorer.score(scheme, results)
    assert score == 100.0
    assert status == MatchStatus.ELIGIBLE


def test_mandatory_fail_ineligible():
    scheme = _scheme([{"mandatory": True, "weight": 50}, {"mandatory": False, "weight": 50}])
    results = [("R00", RuleResult.FAIL, "fail"), ("R01", RuleResult.PASS, "ok")]
    score, status = ConfidenceScorer.score(scheme, results)
    assert status == MatchStatus.INELIGIBLE


def test_ambiguous_scores_half_weight():
    scheme = _scheme([{"mandatory": False, "weight": 50}, {"mandatory": True, "weight": 50}])
    results = [("R00", RuleResult.AMBIGUOUS, "amb"), ("R01", RuleResult.PASS, "ok")]
    score, status = ConfidenceScorer.score(scheme, results)
    # (0.5*50 + 50) / 100 * 100 = 75.0
    assert abs(score - 75.0) < 0.01
    assert status == MatchStatus.LIKELY_ELIGIBLE


def test_all_missing_returns_insufficient():
    scheme = _scheme([{"mandatory": True, "weight": 100}])
    results = [("R00", RuleResult.MISSING, "missing")]
    score, status = ConfidenceScorer.score(scheme, results)
    assert status == MatchStatus.INSUFFICIENT_DATA


def test_mandatory_ambiguous_is_ambiguous_status():
    scheme = _scheme([{"mandatory": True, "weight": 50}, {"mandatory": True, "weight": 50}])
    results = [("R00", RuleResult.AMBIGUOUS, "amb"), ("R01", RuleResult.PASS, "ok")]
    score, status = ConfidenceScorer.score(scheme, results)
    assert status == MatchStatus.AMBIGUOUS


def test_below_40_ineligible():
    scheme = _scheme([{"mandatory": False, "weight": 80}, {"mandatory": False, "weight": 20}])
    results = [("R00", RuleResult.FAIL, "fail"), ("R01", RuleResult.PASS, "ok")]
    # (20) / 100 * 100 = 20.0 → INELIGIBLE (below 40, no mandatory fail but score too low)
    score, status = ConfidenceScorer.score(scheme, results)
    assert score == 20.0
    assert status == MatchStatus.INELIGIBLE


def test_score_between_70_and_90_likely():
    scheme = _scheme([{"mandatory": False, "weight": 20}, {"mandatory": True, "weight": 80}])
    results = [("R00", RuleResult.FAIL, "fail"), ("R01", RuleResult.PASS, "ok")]
    # 80 / 100 * 100 = 80.0 → LIKELY_ELIGIBLE
    score, status = ConfidenceScorer.score(scheme, results)
    assert abs(score - 80.0) < 0.01
    assert status == MatchStatus.LIKELY_ELIGIBLE


def test_coverage_shrinkage_partial_data():
    """Bayesian shrinkage: all-PASS but only 50% of rules evaluated → <100%."""
    scheme = _scheme([
        {"mandatory": True, "weight": 50},   # will be evaluated (PASS)
        {"mandatory": False, "weight": 50},  # will be MISSING
    ])
    results = [("R00", RuleResult.PASS, "ok"), ("R01", RuleResult.MISSING, "?")]
    score, status = ConfidenceScorer.score(scheme, results)
    # raw_score = 50/50 = 1.0, coverage = 50/100 = 0.5
    # confidence = (0.5 + (1.0 - 0.5) * 0.5) * 100 = 75.0 (not 100%)
    assert abs(score - 75.0) < 0.01
    assert status == MatchStatus.LIKELY_ELIGIBLE  # 75 >= 70


def test_full_coverage_no_shrinkage():
    """At coverage=1.0, coverage factor has no effect."""
    scheme = _scheme([{"mandatory": True, "weight": 100}])
    results = [("R00", RuleResult.PASS, "ok")]
    score, status = ConfidenceScorer.score(scheme, results)
    assert score == 100.0
    assert status == MatchStatus.ELIGIBLE
