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
    reason_hi: str       # Hindi
    where_to_go: str     # Plain language: "any bank branch"
    where_to_go_hi: str  # Hindi
    time_estimate: str   # "1 day", "15 days", etc.
    time_estimate_hi: str  # Hindi
    benefit_headline: str
    benefit_headline_hi: str = ""


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
        "where_hi": "किसी भी बैंक शाखा में (SBI, PNB, UCO, आदि)",
        "time": "1–3 days",
        "time_hi": "1–3 दिन",
        "reason": "Opens DBT — unlocks every other scheme",
        "reason_hi": "DBT खाता खुलता है — बाकी सभी योजनाओं के लिए ज़रूरी",
    },
    "nfsa": {
        "icon": "🍚",
        "where": "Food & Civil Supplies dept / Gram Panchayat",
        "where_hi": "खाद्य एवं नागरिक आपूर्ति विभाग / ग्राम पंचायत",
        "time": "15–30 days",
        "time_hi": "15–30 दिन",
        "reason": "Ration card doubles as proof for Ujjwala and Ayushman Bharat",
        "reason_hi": "राशन कार्ड उज्ज्वला और आयुष्मान भारत के लिए पहचान प्रमाण का काम करता है",
    },
    "ayushman_bharat": {
        "icon": "🏥",
        "where": "Any empanelled hospital or CSC",
        "where_hi": "किसी भी सूचीबद्ध अस्पताल या जन सेवा केंद्र (CSC)",
        "time": "Same day with Aadhaar",
        "time_hi": "आधार से उसी दिन",
        "reason": "₹5 lakh free health cover — no waiting period",
        "reason_hi": "₹5 लाख मुफ़्त स्वास्थ्य बीमा — नामांकन के बाद तुरंत लाभ",
    },
    "mgnrega": {
        "icon": "⛏️",
        "where": "Gram Panchayat",
        "where_hi": "ग्राम पंचायत कार्यालय",
        "time": "Job card in 15 days",
        "time_hi": "15 दिन में जॉब कार्ड",
        "reason": "Guaranteed paid work whenever needed — no deadline",
        "reason_hi": "जब चाहें काम मांगें — कोई अंतिम तारीख नहीं, मजदूरी गारंटीशुदा",
    },
    "pm_kisan": {
        "icon": "🌾",
        "where": "pmkisan.gov.in or CSC",
        "where_hi": "pmkisan.gov.in या जन सेवा केंद्र (CSC)",
        "time": "Online application in 10 minutes",
        "time_hi": "10 मिनट में ऑनलाइन आवेदन",
        "reason": "₹6,000/year DBT — needs bank account first",
        "reason_hi": "₹6,000/साल सीधे खाते में — पहले बैंक खाता ज़रूरी",
    },
    "ujjwala": {
        "icon": "🔥",
        "where": "Any LPG distributor (HP / Indane / Bharat Gas)",
        "where_hi": "HP, Indane, या Bharat Gas के किसी भी वितरक के पास",
        "time": "7–15 days",
        "time_hi": "7–15 दिन",
        "reason": "Free LPG connection + ongoing subsidy",
        "reason_hi": "मुफ़्त गैस कनेक्शन + पहला सिलेंडर मुफ़्त",
    },
    "nsap_ignoaps": {
        "icon": "👴",
        "where": "Block Development Office / Gram Panchayat",
        "where_hi": "खंड विकास कार्यालय / ग्राम पंचायत",
        "time": "1–3 months",
        "time_hi": "1–3 महीने",
        "reason": "Monthly pension — apply early, processing takes time",
        "reason_hi": "मासिक पेंशन — जल्दी आवेदन करें, प्रक्रिया में समय लगता है",
    },
    "nsap_ignwps": {
        "icon": "👩",
        "where": "Block Development Office / Gram Panchayat",
        "where_hi": "खंड विकास कार्यालय / ग्राम पंचायत",
        "time": "1–3 months",
        "time_hi": "1–3 महीने",
        "reason": "Monthly widow pension",
        "reason_hi": "विधवा महिलाओं के लिए मासिक पेंशन",
    },
    "nsap_igndps": {
        "icon": "♿",
        "where": "Block Development Office / Gram Panchayat",
        "where_hi": "खंड विकास कार्यालय / ग्राम पंचायत",
        "time": "1–3 months",
        "time_hi": "1–3 महीने",
        "reason": "Monthly disability pension",
        "reason_hi": "विकलांगता पेंशन, हर महीने सीधे खाते में",
    },
    "pmay_g": {
        "icon": "🏠",
        "where": "Gram Panchayat / PMAY portal",
        "where_hi": "ग्राम पंचायत / PMAY पोर्टल",
        "time": "Several months (approval + construction)",
        "time_hi": "कई महीने (स्वीकृति + निर्माण)",
        "reason": "Housing takes time — start early",
        "reason_hi": "मकान बनने में समय लगता है — आवेदन जल्दी करें",
    },
    "pmay_u": {
        "icon": "🏙️",
        "where": "Urban Local Body (ULB) / City Corporation",
        "where_hi": "नगर निगम / शहरी स्थानीय निकाय",
        "time": "Several months",
        "time_hi": "कई महीने",
        "reason": "Urban housing assistance",
        "reason_hi": "शहरी आवास सहायता — होम लोन पर ब्याज सब्सिडी",
    },
    "pm_vishwakarma": {
        "icon": "🔨",
        "where": "pmvishwakarma.gov.in / CSC",
        "where_hi": "pmvishwakarma.gov.in / जन सेवा केंद्र",
        "time": "Register + training first, loan after",
        "time_hi": "पहले पंजीकरण + प्रशिक्षण, फिर ऋण",
        "reason": "₹1 lakh at 5% + tools — choose before MUDRA/PMEGP",
        "reason_hi": "5% ब्याज पर ₹1 लाख + ₹15,000 टूलकिट — MUDRA से पहले तय करें",
    },
    "pm_mudra": {
        "icon": "💼",
        "where": "Any scheduled bank / NBFC / MFI",
        "where_hi": "कोई भी बैंक / NBFC / माइक्रोफाइनेंस संस्था",
        "time": "7–30 days",
        "time_hi": "7–30 दिन",
        "reason": "Working capital for business — up to ₹20 lakh",
        "reason_hi": "व्यवसाय के लिए ₹20 लाख तक — बिना गिरवी के",
    },
    "pmegp": {
        "icon": "🏭",
        "where": "KVIC / DIC (District Industries Centre)",
        "where_hi": "KVIC / जिला उद्योग केंद्र (DIC)",
        "time": "3–6 months (training mandatory)",
        "time_hi": "3–6 महीने (प्रशिक्षण अनिवार्य)",
        "reason": "15–35% free subsidy on project cost",
        "reason_hi": "परियोजना लागत का 15–35% सब्सिडी मुफ़्त",
    },
    "pm_svanidhi": {
        "icon": "🛒",
        "where": "Any scheduled bank / MFI / ULB",
        "where_hi": "कोई भी बैंक / MFI / नगर निगम",
        "time": "7–15 days",
        "time_hi": "7–15 दिन",
        "reason": "₹10,000 working capital — no collateral",
        "reason_hi": "₹10,000 बिना गिरवी के — रेहड़ी-पटरी वालों के लिए",
    },
    "apy": {
        "icon": "📊",
        "where": "Any bank branch where you have an account",
        "where_hi": "जिस बैंक में खाता है उसी शाखा में",
        "time": "Same day enrollment",
        "time_hi": "उसी दिन नामांकन",
        "reason": "Pension savings — start young, govt matches contributions",
        "reason_hi": "जितनी कम उम्र में शुरू, उतनी कम किस्त — सरकार बराबर देती है",
    },
    "pm_sym": {
        "icon": "👷",
        "where": "CSC or bank",
        "where_hi": "जन सेवा केंद्र या बैंक",
        "time": "Same day enrollment",
        "time_hi": "उसी दिन नामांकन",
        "reason": "₹3,000/month pension — govt pays 50%",
        "reason_hi": "₹3,000/माह पेंशन — सरकार 50% किस्त भरती है",
    },
    "sukanya_samriddhi": {
        "icon": "👧",
        "where": "Post office or authorized bank",
        "where_hi": "पोस्ट ऑफिस या अधिकृत बैंक",
        "time": "Same day",
        "time_hi": "उसी दिन",
        "reason": "Best savings rate (8.2%) — open before daughter turns 10",
        "reason_hi": "सबसे ज़्यादा ब्याज (8.2%) — बेटी के 10 वर्ष से पहले खुलवाएं",
    },
    "pmmvy": {
        "icon": "🤰",
        "where": "Anganwadi / CSC",
        "where_hi": "आंगनवाड़ी केंद्र / जन सेवा केंद्र",
        "time": "Apply at ANC registration",
        "time_hi": "गर्भावस्था पंजीकरण के समय आवेदन करें",
        "reason": "₹5,000 maternity benefit — apply during pregnancy",
        "reason_hi": "₹5,000 मातृत्व लाभ — गर्भावस्था में आवेदन ज़रूरी",
    },
    "stand_up_india": {
        "icon": "🚀",
        "where": "Any scheduled commercial bank branch",
        "where_hi": "किसी भी अनुसूचित वाणिज्यिक बैंक शाखा में",
        "time": "Several weeks",
        "time_hi": "कई सप्ताह",
        "reason": "₹10L–₹1Cr for new business — SC/ST or women only",
        "reason_hi": "नए व्यवसाय के लिए ₹10 लाख–₹1 करोड़ — SC/ST या महिला उद्यमी",
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
                reason_hi=meta.get("reason_hi", ""),
                where_to_go=meta.get("where", "Visit local government office"),
                where_to_go_hi=meta.get("where_hi", "स्थानीय सरकारी कार्यालय"),
                time_estimate=meta.get("time", "Varies"),
                time_estimate_hi=meta.get("time_hi", ""),
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
