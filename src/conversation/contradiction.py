"""Detects logical contradictions in user-provided profile data."""
from dataclasses import dataclass


@dataclass
class Contradiction:
    fields: list[str]
    description: str
    suggestion: str


def detect_contradictions(profile_data: dict) -> list[Contradiction]:
    """Return list of logical contradictions found in profile_data."""
    contradictions = []

    # Rural state + urban flag
    rural_states = {"Jharkhand", "Chhattisgarh", "Uttarakhand"}
    state = profile_data.get("state", "")
    is_urban = profile_data.get("is_urban")
    if state in rural_states and is_urban is True:
        contradictions.append(Contradiction(
            fields=["state", "is_urban"],
            description=f"{state} is predominantly rural, but you marked urban=True.",
            suggestion="Please confirm: do you live in a city/town within this state?",
        ))

    # Income tax payer + very low income
    income = profile_data.get("annual_income")
    is_tax_payer = profile_data.get("is_income_tax_payer")
    if income is not None and is_tax_payer is True and income < 250000:
        contradictions.append(Contradiction(
            fields=["annual_income", "is_income_tax_payer"],
            description=f"Income ₹{income:,}/year is below the tax threshold (₹2.5L) but you marked income_tax_payer=True.",
            suggestion="Please verify: do you file ITR (income tax return)?",
        ))

    # Government employee + very low income
    is_govt = profile_data.get("is_govt_employee")
    if income is not None and is_govt is True and income < 60000:
        contradictions.append(Contradiction(
            fields=["annual_income", "is_govt_employee"],
            description=f"Income ₹{income:,}/year seems low for a government employee.",
            suggestion="Please verify your annual income including all allowances.",
        ))

    # Aadhaar-linked bank but no bank account
    has_bank = profile_data.get("has_bank_account")
    is_linked = profile_data.get("is_aadhaar_linked")
    if has_bank is False and is_linked is True:
        contradictions.append(Contradiction(
            fields=["has_bank_account", "is_aadhaar_linked"],
            description="You said you don't have a bank account, but marked Aadhaar as linked to bank.",
            suggestion="Aadhaar-bank linking requires a bank account. Please clarify.",
        ))

    # Age + marital status (under 18 married)
    age = profile_data.get("age")
    marital = profile_data.get("marital_status")
    if age is not None and age < 18 and marital in ("married", "widowed", "divorced"):
        contradictions.append(Contradiction(
            fields=["age", "marital_status"],
            description=f"Age={age} but marital_status={marital}. Legal marriage age is 18.",
            suggestion="Please verify age and marital status.",
        ))

    return contradictions
