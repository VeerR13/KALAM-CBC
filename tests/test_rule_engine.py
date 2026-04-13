"""Tests for rule engine — one test per condition type + scheme integration test."""
import pytest
from src.models.scheme import Rule, RuleCondition, RuleResult, Scheme
from src.models.user_profile import UserProfile
from src.engine.rule_engine import evaluate_rule, evaluate_scheme
from src.loader import load_scheme


def _profile(**kwargs) -> UserProfile:
    defaults = dict(
        age=34, state="Rajasthan", is_urban=False, caste_category="SC",
        gender="M", annual_income=80000, occupation="farmer", family_size=5,
        has_bank_account=True, has_aadhaar=True, is_aadhaar_linked=True,
        land_ownership="owns", land_area_hectares=0.8,
    )
    defaults.update(kwargs)
    return UserProfile(**defaults)


def _rule(condition: dict, mandatory: bool = True, weight: int = 10) -> Rule:
    return Rule(rule_id="TEST", parameter="test", description="test",
                condition=RuleCondition(**condition), is_mandatory=mandatory, weight=weight)


def test_field_check_pass():
    rule = _rule({"type": "field_check", "field": "land_ownership",
                  "values": ["owns"], "ambiguous_values": ["leases", "sharecrop"]})
    result, _ = evaluate_rule(rule, _profile(land_ownership="owns"))
    assert result == RuleResult.PASS


def test_field_check_ambiguous():
    rule = _rule({"type": "field_check", "field": "land_ownership",
                  "values": ["owns"], "ambiguous_values": ["leases", "sharecrop"]})
    result, _ = evaluate_rule(rule, _profile(land_ownership="leases"))
    assert result == RuleResult.AMBIGUOUS


def test_field_check_fail():
    rule = _rule({"type": "field_check", "field": "land_ownership",
                  "values": ["owns"], "ambiguous_values": []})
    result, _ = evaluate_rule(rule, _profile(land_ownership="none"))
    assert result == RuleResult.FAIL


def test_missing_optional_field_returns_missing():
    rule = _rule({"type": "range_check", "field": "disability_percent", "min": 40.0, "max": 100.0})
    result, _ = evaluate_rule(rule, _profile())  # disability_percent=None
    assert result == RuleResult.MISSING


def test_range_check_pass():
    rule = _rule({"type": "range_check", "field": "age", "min": 18.0, "max": 40.0})
    result, _ = evaluate_rule(rule, _profile(age=30))
    assert result == RuleResult.PASS


def test_range_check_fail_above():
    rule = _rule({"type": "range_check", "field": "age", "min": 18.0, "max": 40.0})
    result, _ = evaluate_rule(rule, _profile(age=50))
    assert result == RuleResult.FAIL


def test_range_check_fail_below():
    rule = _rule({"type": "range_check", "field": "age", "min": 18.0, "max": 40.0})
    result, _ = evaluate_rule(rule, _profile(age=15))
    assert result == RuleResult.FAIL


def test_exclusion_fails_when_true():
    rule = _rule({"type": "exclusion",
                  "any_true_fails": [{"field": "is_income_tax_payer", "equals": True}]})
    result, _ = evaluate_rule(rule, _profile(is_income_tax_payer=True))
    assert result == RuleResult.FAIL


def test_exclusion_passes_when_false():
    rule = _rule({"type": "exclusion",
                  "any_true_fails": [{"field": "is_income_tax_payer", "equals": True}]})
    result, _ = evaluate_rule(rule, _profile(is_income_tax_payer=False))
    assert result == RuleResult.PASS


def test_exclusion_missing_field_does_not_fail():
    rule = _rule({"type": "exclusion",
                  "any_true_fails": [{"field": "is_income_tax_payer", "equals": True}]})
    result, _ = evaluate_rule(rule, _profile())  # is_income_tax_payer=None
    assert result == RuleResult.PASS


def test_boolean_check_pass():
    rule = _rule({"type": "boolean_check", "field": "has_bank_account", "equals": True})
    result, _ = evaluate_rule(rule, _profile(has_bank_account=True))
    assert result == RuleResult.PASS


def test_boolean_check_fail():
    rule = _rule({"type": "boolean_check", "field": "has_bank_account", "equals": True})
    result, _ = evaluate_rule(rule, _profile(has_bank_account=False))
    assert result == RuleResult.FAIL


def test_composite_or_pass_if_one_matches():
    rule = _rule({"type": "composite", "logic": "OR", "sub_conditions": [
        {"type": "field_check", "field": "caste_category", "values": ["SC", "ST"], "ambiguous_values": []},
        {"type": "field_check", "field": "gender", "values": ["F"], "ambiguous_values": []},
    ]})
    result, _ = evaluate_rule(rule, _profile(caste_category="SC", gender="M"))
    assert result == RuleResult.PASS


def test_composite_or_fail_if_none_match():
    rule = _rule({"type": "composite", "logic": "OR", "sub_conditions": [
        {"type": "field_check", "field": "caste_category", "values": ["SC", "ST"], "ambiguous_values": []},
        {"type": "field_check", "field": "gender", "values": ["F"], "ambiguous_values": []},
    ]})
    result, _ = evaluate_rule(rule, _profile(caste_category="General", gender="M"))
    assert result == RuleResult.FAIL


def test_evaluate_scheme_pm_kisan():
    scheme_data = load_scheme("pm_kisan")
    scheme = Scheme(**scheme_data)
    profile = _profile(land_ownership="owns", is_income_tax_payer=False, is_govt_employee=False)
    results = evaluate_scheme(scheme, profile)
    assert len(results) == len(scheme.rules)
    for rule_id, result, explanation in results:
        assert isinstance(result, RuleResult)
        assert isinstance(explanation, str)
        assert len(explanation) > 0


def test_evaluate_scheme_mgnrega_rural_adult_eligible():
    scheme_data = load_scheme("mgnrega")
    scheme = Scheme(**scheme_data)
    profile = _profile(is_urban=False, age=34, has_aadhaar=True)
    results = evaluate_scheme(scheme, profile)
    statuses = {rid: res for rid, res, _ in results}
    # All mandatory rules should PASS for a rural adult with Aadhaar
    assert all(r == RuleResult.PASS for r in statuses.values())


def test_evaluate_scheme_mgnrega_urban_fails():
    scheme_data = load_scheme("mgnrega")
    scheme = Scheme(**scheme_data)
    profile = _profile(is_urban=True)
    results = evaluate_scheme(scheme, profile)
    statuses = {rid: res for rid, res, _ in results}
    assert RuleResult.FAIL in statuses.values()
