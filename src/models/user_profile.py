"""Pydantic UserProfile model with unit normalization."""
from typing import Literal, Optional
from pydantic import BaseModel, Field

BIGHA_TO_HECTARES: dict[str, float] = {
    "Rajasthan": 0.4,
    "UP": 0.33,
    "Uttar Pradesh": 0.33,
    "Bihar": 0.33,
    "Assam": 0.625,
    "Jharkhand": 0.33,
    "Madhya Pradesh": 0.33,
    "MP": 0.33,
    "West Bengal": 0.133,
    "Punjab": 0.553,
    "Haryana": 0.553,
    "Gujarat": 0.259,
}
DEFAULT_BIGHA_HECTARES = 0.4

# 1 gaj = 1 sq yard = 0.83612736 sq m = 0.000083612736 ha
GAJ_TO_HECTARES: float = 0.000083612736

# 1 sq ft = 0.09290304 sq m = 0.000009290304 ha
SQFT_TO_HECTARES: float = 0.000009290304


def normalize_bigha_to_hectares(bigha: float, state: str) -> float:
    """Convert bigha to hectares using state-specific conversion factor."""
    factor = BIGHA_TO_HECTARES.get(state, DEFAULT_BIGHA_HECTARES)
    return round(bigha * factor, 4)


def normalize_gaj_to_hectares(gaj: float) -> float:
    """Convert gaj (square yards) to hectares. 1 gaj = 1 sq yard."""
    return round(gaj * GAJ_TO_HECTARES, 6)


def normalize_sqft_to_hectares(sqft: float) -> float:
    """Convert square feet to hectares."""
    return round(sqft * SQFT_TO_HECTARES, 6)


class UserProfile(BaseModel):
    """Complete user profile for welfare eligibility evaluation.
    All fields are Optional — engine returns MISSING for absent fields,
    schemes show INSUFFICIENT_DATA instead of blocking the user.
    """
    # Previously required — now all Optional so the engine works with partial data
    age: Optional[int] = Field(None, ge=0, le=150)
    state: Optional[str] = None
    is_urban: Optional[bool] = None
    caste_category: Optional[Literal["General", "OBC", "SC", "ST"]] = None
    gender: Optional[Literal["M", "F", "Transgender"]] = None
    annual_income: Optional[int] = Field(None, ge=0)
    occupation: Optional[str] = None
    family_size: Optional[int] = Field(None, ge=1)
    has_bank_account: Optional[bool] = None
    has_aadhaar: Optional[bool] = None
    is_aadhaar_linked: Optional[bool] = None

    # Conditional / Optional
    district: Optional[str] = None
    marital_status: Optional[Literal["unmarried", "married", "widowed", "divorced", "separated"]] = None
    land_ownership: Optional[Literal["owns", "leases", "sharecrop", "none"]] = None
    land_area_hectares: Optional[float] = None
    num_children: Optional[int] = None
    has_girl_child_under_10: Optional[bool] = None
    is_pregnant_or_lactating: Optional[bool] = None
    num_live_births: Optional[int] = None
    has_ration_card: Optional[Literal["AAY", "PHH", "none", "unknown"]] = None
    disability_percent: Optional[int] = Field(None, ge=0, le=100)
    is_govt_employee: Optional[bool] = None
    is_income_tax_payer: Optional[bool] = None
    has_existing_enterprise: Optional[bool] = None
    is_epf_member: Optional[bool] = None
    previous_scheme_loans: Optional[list[str]] = None

    # Wealth exclusion indicators (used to evaluate PMJAY, PMAY-G, and other BPL exclusion criteria)
    has_motorized_vehicle: Optional[bool] = None          # 2/3/4-wheeler or motorized fishing boat
    has_mechanized_farm_equipment: Optional[bool] = None  # tractor, thresher, etc.
    has_kisan_credit_card: Optional[bool] = None          # KCC with credit limit ≥₹50,000
    has_refrigerator: Optional[bool] = None
    has_landline: Optional[bool] = None
    has_pucca_house: Optional[bool] = None                # permanent/solidly-built house

    # Metadata
    income_is_approximate: bool = False
    income_range: Optional[tuple[int, int]] = None
