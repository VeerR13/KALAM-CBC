"""Personalized benefit calculator — returns exact rupee/service values per eligible scheme."""
import json
from dataclasses import dataclass
from pathlib import Path
from src.models.user_profile import UserProfile

_STATE_DATA_PATH = Path(__file__).parent.parent.parent / "data" / "state_data.json"
_STATE_DATA_CACHE: dict | None = None


def _load_state_data() -> dict:
    global _STATE_DATA_CACHE
    if _STATE_DATA_CACHE is None:
        try:
            _STATE_DATA_CACHE = json.loads(_STATE_DATA_PATH.read_text())
        except Exception:
            _STATE_DATA_CACHE = {}
    return _STATE_DATA_CACHE


def _state_key(state: str) -> str:
    return state.lower().replace(" ", "_").replace("&", "and").replace("-", "_")

# MGNREGA daily wages by state (FY 2024-25, Ministry of Rural Development)
MGNREGA_WAGES: dict[str, int] = {
    "Andhra Pradesh": 257, "Arunachal Pradesh": 234, "Assam": 213,
    "Bihar": 228, "Chhattisgarh": 221, "Goa": 356, "Gujarat": 256,
    "Haryana": 357, "Himachal Pradesh": 266, "Jharkhand": 237,
    "Karnataka": 349, "Kerala": 349, "Madhya Pradesh": 221,
    "Maharashtra": 273, "Manipur": 238, "Meghalaya": 226,
    "Mizoram": 249, "Nagaland": 234, "Odisha": 237, "Punjab": 303,
    "Rajasthan": 255, "Sikkim": 234, "Tamil Nadu": 294,
    "Telangana": 257, "Tripura": 225, "Uttarakhand": 213,
    "Uttar Pradesh": 237, "West Bengal": 237,
    "Jammu and Kashmir": 259, "J&K": 259, "Ladakh": 259,
    "Andaman and Nicobar Islands": 326, "Chandigarh": 357,
    "Delhi": 746, "Puducherry": 294,
}
DEFAULT_WAGE = 250

HILLY_NE_STATES = {
    "Himachal Pradesh", "Uttarakhand", "Jammu and Kashmir", "J&K", "Ladakh",
    "Arunachal Pradesh", "Assam", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Sikkim", "Tripura",
    "Andaman and Nicobar Islands",
}

# APY base monthly contribution for ₹1,000/month pension tier (age at entry)
APY_BASE: dict[int, int] = {
    18: 42, 19: 46, 20: 50, 21: 54, 22: 59, 23: 64, 24: 70,
    25: 76, 26: 82, 27: 90, 28: 97, 29: 106, 30: 116,
    31: 126, 32: 138, 33: 151, 34: 165, 35: 181,
    36: 198, 37: 218, 38: 240, 39: 264, 40: 291,
}

# PM-SYM monthly contribution by entry age (for ₹3,000/month pension)
PMSYM_CONTRIB: dict[int, int] = {
    18: 55, 19: 58, 20: 61, 21: 64, 22: 68, 23: 72, 24: 76,
    25: 80, 26: 85, 27: 90, 28: 95, 29: 100, 30: 105,
    31: 110, 32: 120, 33: 130, 34: 140, 35: 150, 36: 160,
    37: 170, 38: 180, 39: 190, 40: 200,
}


@dataclass
class BenefitDisplay:
    primary: str = ""           # Large-print headline, e.g. "₹6,000 per year"
    secondary: str = ""         # Supporting detail line
    annual_value: int = 0       # Rupee value for summing totals (0 = non-cash)
    value_type: str = "service" # cash | insurance | housing | loan | subsidy | food | service
    note: str = ""              # projections, caveats, tips


def _fmt(n: int) -> str:
    if n >= 10_00_000:
        v = n / 1_00_000
        return f"₹{v:.1f} lakh" if v != int(v) else f"₹{int(v)} lakh"
    return f"₹{n:,}"


def calculate_benefit(scheme_id: str, profile: UserProfile) -> BenefitDisplay:
    age = profile.age or 30
    state = profile.state or ""
    family_size = profile.family_size or 4
    is_urban = profile.is_urban if profile.is_urban is not None else False
    income = profile.annual_income or 0
    caste = profile.caste_category or "General"
    gender = profile.gender or "M"

    match scheme_id:
        case "pm_kisan":
            return BenefitDisplay(
                primary="₹6,000 per year",
                secondary="₹2,000 every 4 months — direct to your bank account",
                annual_value=6000,
                value_type="cash",
                note="Over 5 years: ₹30,000 total",
            )

        case "mgnrega":
            wage = MGNREGA_WAGES.get(state, DEFAULT_WAGE)
            annual = wage * 100
            return BenefitDisplay(
                primary=f"100 days work/year at ₹{wage}/day",
                secondary=f"Potential annual earning: {_fmt(annual)}",
                annual_value=annual,
                value_type="cash",
                note="Wages paid to bank within 15 days. Guaranteed by law.",
            )

        case "ayushman_bharat":
            return BenefitDisplay(
                primary="₹5,00,000 health cover / year",
                secondary="Free hospitalization, surgery, medicines — zero payment at hospital",
                annual_value=0,
                value_type="insurance",
                note=f"Covers your whole family. Valid at any empanelled hospital across India.",
            )

        case "pmay_g":
            amount = 130000 if state in HILLY_NE_STATES else 120000
            wage = MGNREGA_WAGES.get(state, DEFAULT_WAGE)
            total = amount + 12000 + 95 * wage
            return BenefitDisplay(
                primary=f"{_fmt(amount)} to build a pucca house",
                secondary=f"+ ₹12,000 toilet (SBM) + 95 days MGNREGA wages + free LPG",
                annual_value=amount,
                value_type="housing",
                note=f"Total package value: ~{_fmt(total)}",
            )

        case "pmay_u":
            if income <= 300000:
                tier, detail = "EWS", "Central assistance for house construction (BLC/AHP)"
            elif income <= 600000:
                tier, detail = "LIG", "Interest subsidy on home loan (BLC/AHP vertical)"
            else:
                tier, detail = "MIG", "Interest subsidy on home loan"
            return BenefitDisplay(
                primary=f"{tier} beneficiary",
                secondary=detail,
                annual_value=0,
                value_type="housing",
                note="House in female head's name. Carpet area 30–90 sqm, value up to ₹45 lakh.",
            )

        case "pmjdy":
            parts = "Free zero-balance account + RuPay card + ₹1,00,000 accident cover"
            note = ""
            if 18 <= age <= 59:
                parts += " + ₹30,000 life insurance"
                note = "Life cover for earning head of family aged 18–59."
            return BenefitDisplay(
                primary="Free bank account + insurance",
                secondary=parts,
                annual_value=0,
                value_type="service",
                note=note,
            )

        case "ujjwala":
            return BenefitDisplay(
                primary="Free LPG connection + first cylinder free",
                secondary="Ongoing subsidy credited to your bank account on refills",
                annual_value=0,
                value_type="service",
                note="Saves ~₹3,000–5,000/year compared to wood or coal.",
            )

        case "nsap_ignoaps":
            central = 500 if age >= 80 else 200
            sd = _load_state_data().get(_state_key(state), {})
            topup = sd.get("nsap_old_age_topup", 0) or 0
            total = central + topup
            if topup:
                note = f"{state} adds ₹{topup:,}/month on top. Total: ₹{total:,}/month = ₹{total*12:,}/year."
                secondary = f"₹{central}/month central + ₹{topup}/month {state} = ₹{total}/month"
            else:
                note = "State top-ups range ₹0–₹2,500+/month. Delhi adds ₹2,500, Kerala adds ₹1,600."
                secondary = f"₹{central * 12:,}/year central govt — your state may add more"
            return BenefitDisplay(
                primary=f"₹{total}/month pension" if topup else f"₹{central}/month pension (central govt)",
                secondary=secondary,
                annual_value=total * 12,
                value_type="cash",
                note=note,
            )

        case "nsap_ignwps":
            central = 500 if age >= 80 else 300
            sd = _load_state_data().get(_state_key(state), {})
            topup = sd.get("nsap_widow_topup", 0) or 0
            total = central + topup
            if topup:
                secondary = f"₹{central}/month central + ₹{topup}/month {state} = ₹{total}/month"
                note = f"Total ₹{total*12:,}/year. Pension stops if you remarry."
            else:
                secondary = f"₹{central * 12:,}/year from central govt + state top-up"
                note = "Pension stops if you remarry."
            return BenefitDisplay(
                primary=f"₹{total}/month widow pension" if topup else f"₹{central}/month widow pension",
                secondary=secondary,
                annual_value=total * 12,
                value_type="cash",
                note=note,
            )

        case "nsap_igndps":
            central = 500 if age >= 80 else 300
            sd = _load_state_data().get(_state_key(state), {})
            topup = sd.get("nsap_disability_topup", 0) or 0
            total = central + topup
            if topup:
                secondary = f"₹{central}/month central + ₹{topup}/month {state} = ₹{total}/month"
            else:
                secondary = f"₹{central * 12:,}/year from central govt + state top-up"
            return BenefitDisplay(
                primary=f"₹{total}/month disability pension" if topup else f"₹{central}/month disability pension",
                secondary=secondary,
                annual_value=total * 12,
                value_type="cash",
            )

        case "apy":
            entry_age = min(max(age, 18), 40)
            base = APY_BASE.get(entry_age, APY_BASE[30])
            years = 60 - entry_age
            return BenefitDisplay(
                primary="₹1,000–5,000/month pension after age 60",
                secondary=f"At age {entry_age}: pay ~₹{base}/month → get ₹1,000/month pension",
                annual_value=0,
                value_type="service",
                note=f"Govt matches your contribution equally. You invest for {years} years.",
            )

        case "pm_sym":
            entry_age = min(max(age, 18), 40)
            contrib = PMSYM_CONTRIB.get(entry_age, 100)
            return BenefitDisplay(
                primary="₹3,000/month after age 60 — guaranteed",
                secondary=f"Pay ₹{contrib}/month now → govt matches equally",
                annual_value=0,
                value_type="service",
                note="For unorganised workers. Govt pays 50%, you pay 50%.",
            )

        case "pm_svanidhi":
            return BenefitDisplay(
                primary="₹10,000 working capital loan — no collateral",
                secondary="Repay in 1 year → ₹20,000 → then ₹50,000",
                annual_value=0,
                value_type="loan",
                note="7% interest subsidy. ₹100/month cashback for digital payments.",
            )

        case "pm_mudra":
            if profile.has_existing_enterprise:
                tier = "Kishore (up to ₹5 lakh) or Tarun (up to ₹10 lakh)"
                note = "Tarun Plus up to ₹20 lakh for successful Tarun repayers."
            else:
                tier = "Shishu: up to ₹50,000 — no collateral, no processing fee"
                note = "Shishu → Kishore (₹5L) → Tarun (₹10L) → Tarun Plus (₹20L)."
            return BenefitDisplay(
                primary=tier,
                secondary="Non-farm enterprise loan through banks / MFIs / NBFCs",
                annual_value=0,
                value_type="loan",
                note=note,
            )

        case "pmegp":
            is_special = caste in ("SC", "ST", "OBC") or gender == "F"
            sub = (35 if not is_urban else 25) if is_special else (25 if not is_urban else 15)
            own = 5 if is_special else 10
            eg = 1000000
            return BenefitDisplay(
                primary=f"{sub}% free government subsidy on project cost",
                secondary=f"₹10L project example: You pay {_fmt(eg * own // 100)}, Govt gives {_fmt(eg * sub // 100)}, Bank loans rest",
                annual_value=0,
                value_type="subsidy",
                note=f"Own contribution only {own}%. No collateral up to ₹10L. Mandatory EDP training.",
            )

        case "stand_up_india":
            return BenefitDisplay(
                primary="₹10 lakh – ₹1 crore for new business",
                secondary="For SC/ST or women entrepreneurs. Greenfield enterprise only.",
                annual_value=0,
                value_type="loan",
                note="Every bank branch must give at least one such loan to SC/ST and one to a woman.",
            )

        case "sukanya_samriddhi":
            return BenefitDisplay(
                primary="8.2% interest — highest government savings rate",
                secondary="Open before daughter turns 10. Save ₹250–₹1.5L/year for 15 years.",
                annual_value=0,
                value_type="service",
                note="At max deposit (₹1.5L/year for 15 years): your daughter could receive ~₹65–70 lakh at age 21. Fully tax-free.",
            )

        case "pmmvy":
            return BenefitDisplay(
                primary="₹5,000 for first child / ₹6,000 for second girl child",
                secondary="₹3,000 after ANC registration + ₹2,000 after birth + vaccination",
                annual_value=5000,
                value_type="cash",
                note="Plus ~₹1,000 from Janani Suraksha Yojana for institutional delivery.",
            )

        case "nfsa":
            if profile.has_ration_card == "AAY":
                savings = int(35 * 22.5 * 12)
                return BenefitDisplay(
                    primary="35 kg grain/month at ₹1–3/kg (AAY yellow card)",
                    secondary=f"Saves ~{_fmt(savings)}/year vs open-market price",
                    annual_value=savings,
                    value_type="food",
                    note="Antyodaya Anna Yojana — for the poorest households.",
                )
            else:
                kg = (family_size) * 5
                savings = int(kg * 22.5 * 12)
                return BenefitDisplay(
                    primary=f"{kg} kg grain/month ({family_size} members × 5 kg)",
                    secondary=f"At ₹1–3/kg — saves ~{_fmt(savings)}/year",
                    annual_value=savings,
                    value_type="food",
                )

        case "pm_vishwakarma":
            return BenefitDisplay(
                primary="₹1 lakh loan at 5% + ₹15,000 tool kit + free training",
                secondary="After repaying: ₹2 lakh more at 5% — no collateral needed",
                annual_value=0,
                value_type="loan",
                note="PM Vishwakarma certificate + digital transaction incentive + market access support.",
            )

        case _:
            return BenefitDisplay()
