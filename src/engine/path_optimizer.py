"""Optimal application path — recommends the best order and flags trade-offs."""
from dataclasses import dataclass, field
from typing import Optional

from src.engine.benefit_calculator import BenefitDisplay, calculate_benefit
from src.engine.confidence import MatchStatus
from src.engine.interaction_detector import Interaction
from src.models.user_profile import UserProfile


@dataclass
class PathStep:
    scheme_id: str
    scheme_name: str
    icon: str
    reason: str          # Why this step comes here
    where_to_go: str     # Plain language: "any bank branch"
    time_estimate: str   # "1 day", "15 days", etc.
    benefit_headline: str


@dataclass
class OptimalPath:
    steps: list[PathStep]
    interactions: list[Interaction]
    total_annual_cash: int
    total_annual_food: int
    total_insurance_cover: int
    summary_lines: list[str]   # 2-3 plain-language summary bullets


_STEP_META: dict[str, dict] = {
    "pmjdy": {
        "icon": "🏦",
        "where": "Any bank branch (SBI, PNB, UCO, etc.)",
        "time": "1–3 days",
        "reason": "Opens DBT — unlocks every other scheme",
    },
    "nfsa": {
        "icon": "🍚",
        "where": "Food & Civil Supplies department / Gram Panchayat",
        "time": "15–30 days",
        "reason": "Ration card doubles as proof for Ujjwala and Ayushman Bharat",
    },
    "ayushman_bharat": {
        "icon": "🏥",
        "where": "Any empanelled hospital or CSC (Common Service Centre)",
        "time": "Same day with Aadhaar",
        "reason": "₹5 lakh free health cover — no waiting period once enrolled",
    },
    "mgnrega": {
        "icon": "⛏️",
        "where": "Gram Panchayat",
        "time": "Job card in 15 days",
        "reason": "Guaranteed paid work whenever needed — no deadline to apply",
    },
    "pm_kisan": {
        "icon": "🌾",
        "where": "pmkisan.gov.in or CSC",
        "time": "Online application in 10 minutes",
        "reason": "₹6,000/year DBT — needs bank account first",
    },
    "ujjwala": {
        "icon": "🔥",
        "where": "Any LPG distributor (HP / Indane / Bharat Gas)",
        "time": "7–15 days",
        "reason": "Free LPG connection + ongoing subsidy",
    },
    "nsap_ignoaps": {
        "icon": "👴",
        "where": "Block Development Office / Gram Panchayat",
        "time": "1–3 months",
        "reason": "Monthly pension — apply early, processing takes time",
    },
    "nsap_ignwps": {
        "icon": "👩",
        "where": "Block Development Office / Gram Panchayat",
        "time": "1–3 months",
        "reason": "Monthly widow pension",
    },
    "nsap_igndps": {
        "icon": "♿",
        "where": "Block Development Office / Gram Panchayat",
        "time": "1–3 months",
        "reason": "Monthly disability pension",
    },
    "pmay_g": {
        "icon": "🏠",
        "where": "Gram Panchayat / PMAY portal",
        "time": "Several months (approval + construction)",
        "reason": "Housing takes time — start the process early",
    },
    "pmay_u": {
        "icon": "🏙️",
        "where": "Urban Local Body (ULB) / City Corporation",
        "time": "Several months",
        "reason": "Urban housing assistance",
    },
    "pm_vishwakarma": {
        "icon": "🔨",
        "where": "pmvishwakarma.gov.in / CSC",
        "time": "Register + training first, loan after",
        "reason": "₹1 lakh at 5% + tools — decide before taking MUDRA/PMEGP",
    },
    "pm_mudra": {
        "icon": "💼",
        "where": "Any scheduled bank / NBFC / MFI",
        "time": "7–30 days",
        "reason": "Working capital for business — up to ₹20 lakh in stages",
    },
    "pmegp": {
        "icon": "🏭",
        "where": "KVIC / DIC (District Industries Centre)",
        "time": "3–6 months (training mandatory)",
        "reason": "15–35% free subsidy on project cost",
    },
    "pm_svanidhi": {
        "icon": "🛒",
        "where": "Any scheduled bank / MFI / ULB",
        "time": "7–15 days",
        "reason": "₹10,000 working capital for street vendors — no collateral",
    },
    "apy": {
        "icon": "📊",
        "where": "Any bank branch where you have an account",
        "time": "Same day enrollment",
        "reason": "Pension savings — start young, government matches contributions",
    },
    "pm_sym": {
        "icon": "👷",
        "where": "CSC or bank",
        "time": "Same day enrollment",
        "reason": "₹3,000/month guaranteed pension — govt pays 50%",
    },
    "sukanya_samriddhi": {
        "icon": "👧",
        "where": "Post office or authorized bank",
        "time": "Same day",
        "reason": "Best savings rate (8.2%) for daughter's future — open before age 10",
    },
    "pmmvy": {
        "icon": "🤰",
        "where": "Anganwadi / CSC",
        "time": "Apply at ANC registration",
        "reason": "₹5,000–6,000 maternity benefit — apply during pregnancy",
    },
    "stand_up_india": {
        "icon": "🚀",
        "where": "Any scheduled commercial bank branch",
        "time": "Several weeks",
        "reason": "₹10L–₹1Cr for new business — SC/ST or women only",
    },
}

# Priority tiers — enablers first, then high-value cash, then insurance, then rest
_PRIORITY_ORDER = [
    # Tier 0 — enablers (must come first)
    "pmjdy", "nfsa",
    # Tier 1 — immediate high-value cash / food
    "pm_kisan", "mgnrega", "nsap_ignoaps", "nsap_ignwps", "nsap_igndps",
    # Tier 2 — insurance / health
    "ayushman_bharat",
    # Tier 3 — housing (long process, start early)
    "pmay_g", "pmay_u",
    # Tier 4 — services
    "ujjwala", "pmmvy", "sukanya_samriddhi",
    # Tier 5 — business / loans (check mutual exclusions first)
    "pm_vishwakarma", "pm_mudra", "pmegp", "pm_svanidhi", "stand_up_india",
    # Tier 6 — long-term savings
    "apy", "pm_sym",
]


class PathOptimizer:
    """Build an optimal, step-by-step application path from eligible scheme IDs."""

    def __init__(self, scheme_name_map: dict[str, str]):
        self._names = scheme_name_map

    def recommend(
        self,
        profile: UserProfile,
        eligible_ids: list[str],
        interactions: list[Interaction],
    ) -> OptimalPath:
        active = set(eligible_ids)

        # Build step ordering respecting the priority tiers
        ordered_ids: list[str] = []
        for sid in _PRIORITY_ORDER:
            if sid in active:
                ordered_ids.append(sid)
        # Append any eligible IDs not in the priority list (shouldn't happen but safety net)
        for sid in eligible_ids:
            if sid not in ordered_ids:
                ordered_ids.append(sid)

        steps: list[PathStep] = []
        for sid in ordered_ids:
            meta = _STEP_META.get(sid, {})
            try:
                benefit = calculate_benefit(sid, profile)
            except Exception:
                benefit = BenefitDisplay()

            steps.append(PathStep(
                scheme_id=sid,
                scheme_name=self._names.get(sid, sid.replace("_", " ").upper()),
                icon=meta.get("icon", "📋"),
                reason=meta.get("reason", ""),
                where_to_go=meta.get("where", "Visit local government office"),
                time_estimate=meta.get("time", "Varies"),
                benefit_headline=benefit.primary or benefit.secondary or "",
            ))

        # Compute totals
        total_cash = 0
        total_food = 0
        total_insurance = 0
        for sid in active:
            try:
                b = calculate_benefit(sid, profile)
                if b.value_type in ("cash", "subsidy"):
                    total_cash += b.annual_value
                elif b.value_type == "food":
                    total_food += b.annual_value
                elif b.value_type == "insurance":
                    total_insurance += 500000  # Ayushman Bharat fixed
            except Exception:
                pass

        summary: list[str] = []
        if total_cash:
            summary.append(f"₹{total_cash:,}/year in direct cash or subsidies")
        if total_food:
            summary.append(f"~₹{total_food:,}/year saved on food (subsidised ration)")
        if total_insurance:
            summary.append(f"₹{total_insurance:,} health insurance coverage")

        return OptimalPath(
            steps=steps,
            interactions=interactions,
            total_annual_cash=total_cash,
            total_annual_food=total_food,
            total_insurance_cover=total_insurance,
            summary_lines=summary,
        )
