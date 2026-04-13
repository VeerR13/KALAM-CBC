"""Bureaucratic distance — computes effort-to-claim per scheme from user's document status."""
from dataclasses import dataclass, field
from typing import Optional

from src.models.scheme import Scheme
from src.models.user_profile import UserProfile


@dataclass
class BureaucraticScore:
    scheme_id: str
    score: int                      # lower = easier
    difficulty_label: str           # easy | moderate | involved | complex
    missing_docs: list[dict]        # doc dicts with name + where_to_obtain + days
    docs_already_have: list[str]    # doc names user already has
    total_days_estimate: int
    offices_to_visit: list[str]
    unmet_prerequisites: list[str]
    can_apply_online: bool


# Map profile boolean fields → document names that can be inferred as "already have"
_PROFILE_TO_DOC_KEYWORDS: list[tuple[str, list[str]]] = [
    ("has_aadhaar",       ["aadhaar", "identity"]),
    ("has_bank_account",  ["bank", "passbook", "account"]),
    ("is_aadhaar_linked", ["aadhaar-linked", "seeded"]),
    ("has_ration_card",   ["ration"]),
]

# Schemes with known online application channels
_ONLINE_SCHEMES = {
    "pm_kisan", "ayushman_bharat", "pmay_g", "pmay_u",
    "pmjdy", "apy", "pm_sym", "pm_mudra", "pm_svanidhi",
    "pm_vishwakarma", "sukanya_samriddhi",
}


def _max_processing_days(days_str: str) -> int:
    """Parse '3-10' or '0' or '7-30' → max int."""
    if not days_str:
        return 0
    parts = str(days_str).replace(" ", "").split("-")
    try:
        return max(int(p) for p in parts if p.isdigit())
    except (ValueError, TypeError):
        return 0


def _user_has_doc(doc_name: str, profile: UserProfile) -> bool:
    """Heuristically check if user already has a document."""
    name_lower = doc_name.lower()
    for field_name, keywords in _PROFILE_TO_DOC_KEYWORDS:
        field_val = getattr(profile, field_name, None)
        if field_val and field_val is not False and field_val != "none":
            if any(kw in name_lower for kw in keywords):
                return True
    # Land records: if user owns land they likely have them
    if "land" in name_lower or "khatauni" in name_lower or "khasra" in name_lower:
        if profile.land_ownership == "owns":
            return True
    # Self-declaration: user can always produce this
    if "self-declaration" in name_lower or "affidavit" in name_lower:
        return False  # requires effort at notary/stamp paper
    return False


class BureaucraticDistanceCalculator:
    """
    All computation is from scheme JSON + user profile.
    Nothing is hardcoded per scheme.
    """

    def calculate(
        self,
        profile: UserProfile,
        scheme: Scheme,
        unmet_prerequisites: list[str],
    ) -> BureaucraticScore:
        required_docs = scheme.required_documents  # list of Document pydantic objects

        missing_docs: list[dict] = []
        has_docs: list[str] = []
        offices: set[str] = set()

        for doc in required_docs:
            doc_name = doc.document
            if _user_has_doc(doc_name, profile):
                has_docs.append(doc_name)
            else:
                days = _max_processing_days(doc.processing_time_days)
                missing_docs.append({
                    "name": doc_name,
                    "where": doc.where_to_obtain,
                    "days": days,
                })
                if doc.where_to_obtain:
                    offices.add(doc.where_to_obtain)

        total_days = sum(d["days"] for d in missing_docs)
        num_offices = len(offices)
        chain = len(unmet_prerequisites)
        can_online = scheme.scheme_id in _ONLINE_SCHEMES

        # Weighted score: lower = easier
        score = (
            len(missing_docs) * 10
            + total_days * 0.5
            + num_offices * 15
            + chain * 20
            + (0 if can_online else 10)
        )

        return BureaucraticScore(
            scheme_id=scheme.scheme_id,
            score=round(score),
            difficulty_label=_label(score),
            missing_docs=missing_docs,
            docs_already_have=has_docs,
            total_days_estimate=total_days,
            offices_to_visit=sorted(offices),
            unmet_prerequisites=unmet_prerequisites,
            can_apply_online=can_online,
        )


def _label(score: float) -> str:
    if score <= 15:
        return "easy"
    if score <= 40:
        return "moderate"
    if score <= 70:
        return "involved"
    return "complex"
