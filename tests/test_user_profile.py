"""Tests for UserProfile model."""
import pytest
from pydantic import ValidationError
from src.models.user_profile import (
    UserProfile,
    normalize_bigha_to_hectares,
    normalize_gaj_to_hectares,
    normalize_sqft_to_hectares,
)


def test_valid_minimal_profile():
    p = UserProfile(
        age=34, state="Rajasthan", is_urban=False,
        caste_category="SC", gender="M",
        annual_income=80000, occupation="farmer",
        family_size=5, has_bank_account=True,
        has_aadhaar=True, is_aadhaar_linked=False,
    )
    assert p.age == 34
    assert p.state == "Rajasthan"


def test_invalid_age_rejected():
    with pytest.raises(ValidationError):
        UserProfile(age=-1, state="UP", is_urban=False,
                    caste_category="OBC", gender="F",
                    annual_income=50000, occupation="farmer",
                    family_size=3, has_bank_account=False,
                    has_aadhaar=False, is_aadhaar_linked=False)


def test_bigha_normalization_rajasthan():
    assert abs(normalize_bigha_to_hectares(2.0, "Rajasthan") - 0.8) < 0.001


def test_bigha_normalization_up():
    assert abs(normalize_bigha_to_hectares(2.0, "UP") - 0.66) < 0.01


def test_bigha_normalization_assam():
    assert abs(normalize_bigha_to_hectares(2.0, "Assam") - 1.25) < 0.001


def test_income_approximate_flag():
    p = UserProfile(
        age=34, state="UP", is_urban=False, caste_category="OBC", gender="M",
        annual_income=85000, occupation="farmer", family_size=4,
        has_bank_account=True, has_aadhaar=True, is_aadhaar_linked=True,
        income_is_approximate=True, income_range=(80000, 90000)
    )
    assert p.income_is_approximate is True
    assert p.income_range == (80000, 90000)


def test_optional_fields_default_none():
    p = UserProfile(
        age=25, state="Bihar", is_urban=False, caste_category="ST", gender="F",
        annual_income=40000, occupation="agricultural_labourer", family_size=4,
        has_bank_account=False, has_aadhaar=True, is_aadhaar_linked=False,
    )
    assert p.land_ownership is None
    assert p.disability_percent is None
    assert p.marital_status is None


def test_invalid_caste_rejected():
    with pytest.raises(ValidationError):
        UserProfile(
            age=30, state="UP", is_urban=False, caste_category="INVALID",
            gender="M", annual_income=50000, occupation="farmer",
            family_size=3, has_bank_account=True, has_aadhaar=True, is_aadhaar_linked=False,
        )


def test_gaj_to_hectares():
    # 200 gaj (sq yards) → 200 × 0.000083612736 = 0.016723 ha
    result = normalize_gaj_to_hectares(200)
    assert abs(result - 0.016723) < 0.0001


def test_sqft_to_hectares():
    # 1000 sqft → 1000 × 0.000009290304 = 0.009290 ha
    result = normalize_sqft_to_hectares(1000)
    assert abs(result - 0.009290) < 0.0001


def test_gaj_round_trip_reasonable():
    # Typical urban plot: 200 gaj ≈ 167 sq meters — well under 2 ha land cap
    assert normalize_gaj_to_hectares(200) < 2.0


def test_disability_percent_bounds():
    with pytest.raises(ValidationError):
        UserProfile(
            age=30, state="UP", is_urban=False, caste_category="SC",
            gender="M", annual_income=50000, occupation="farmer",
            family_size=3, has_bank_account=True, has_aadhaar=True,
            is_aadhaar_linked=False, disability_percent=101,
        )
