"""Tests for follow_up and simple parsing logic."""
from src.conversation.follow_up import get_next_question, missing_mandatory_fields, MANDATORY_FIELDS


def test_all_mandatory_missing_returns_first_question():
    question = get_next_question({})
    assert question is not None
    assert len(question) > 0


def test_no_question_when_all_mandatory_present():
    full_profile = {
        "age": 34, "state": "UP", "is_urban": False, "caste_category": "OBC",
        "gender": "M", "annual_income": 80000, "occupation": "farmer",
        "family_size": 4, "has_bank_account": True, "has_aadhaar": True,
        "is_aadhaar_linked": True,
    }
    assert get_next_question(full_profile) is None


def test_missing_mandatory_fields_all_missing():
    missing = missing_mandatory_fields({})
    assert set(missing) == MANDATORY_FIELDS


def test_missing_mandatory_fields_partial():
    partial = {"age": 34, "state": "UP", "is_urban": False}
    missing = missing_mandatory_fields(partial)
    assert "age" not in missing
    assert "annual_income" in missing


def test_mandatory_fields_count():
    assert len(MANDATORY_FIELDS) == 11
