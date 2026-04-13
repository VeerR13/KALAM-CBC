"""Tests for contradiction detection."""
from src.conversation.contradiction import detect_contradictions, Contradiction


def test_no_contradictions_clean_profile():
    profile = {
        "age": 34, "state": "UP", "is_urban": False, "annual_income": 80000,
        "is_income_tax_payer": False, "is_govt_employee": False,
        "has_bank_account": True, "is_aadhaar_linked": True,
    }
    assert detect_contradictions(profile) == []


def test_aadhaar_linked_without_bank():
    profile = {"has_bank_account": False, "is_aadhaar_linked": True}
    contradictions = detect_contradictions(profile)
    fields_affected = {f for c in contradictions for f in c.fields}
    assert "is_aadhaar_linked" in fields_affected
    assert "has_bank_account" in fields_affected


def test_low_income_but_tax_payer():
    profile = {"annual_income": 100000, "is_income_tax_payer": True}
    contradictions = detect_contradictions(profile)
    assert len(contradictions) >= 1
    assert any("is_income_tax_payer" in c.fields for c in contradictions)


def test_underage_married():
    profile = {"age": 15, "marital_status": "married"}
    contradictions = detect_contradictions(profile)
    assert any("age" in c.fields for c in contradictions)


def test_returns_list_of_contradiction_objects():
    profile = {"has_bank_account": False, "is_aadhaar_linked": True}
    result = detect_contradictions(profile)
    assert all(isinstance(c, Contradiction) for c in result)
