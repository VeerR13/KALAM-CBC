"""Kalam Conversational Engine — stateful, API-free, Hinglish NLU.

Manages multi-turn conversation to collect a UserProfile from natural language.
Handles incomplete answers, contradictions, and users who don't know their data.
No external API calls — pure regex + rule-based extraction.
"""
from __future__ import annotations

import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

from src.conversation.contradiction import detect_contradictions
from src.conversation.follow_up import FIELD_PRIORITY, MANDATORY_FIELDS
from src.models.user_profile import (
    normalize_bigha_to_hectares,
    normalize_gaj_to_hectares,
    normalize_sqft_to_hectares,
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

@dataclass
class ConversationState:
    session_id: str
    profile: dict = field(default_factory=dict)
    skipped: set = field(default_factory=set)
    contradictions_seen: list = field(default_factory=list)
    turn: int = 0
    last_question: Optional[str] = None
    last_question_field: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    done: bool = False          # True once we have enough to show results


# In-memory session store (sufficient for Render free tier single-process)
_SESSIONS: dict[str, ConversationState] = {}
_SESSION_TTL = 3600  # 1 hour


def get_or_create_session(session_id: Optional[str] = None) -> ConversationState:
    now = time.time()
    # Evict expired sessions
    expired = [k for k, v in _SESSIONS.items() if now - v.created_at > _SESSION_TTL]
    for k in expired:
        del _SESSIONS[k]

    if session_id and session_id in _SESSIONS:
        return _SESSIONS[session_id]

    sid = session_id or secrets.token_urlsafe(16)
    state = ConversationState(session_id=sid)
    _SESSIONS[sid] = state
    return state


def reset_session(session_id: str) -> ConversationState:
    state = ConversationState(session_id=session_id)
    _SESSIONS[session_id] = state
    return state


# ---------------------------------------------------------------------------
# Skip / "don't know" detection
# ---------------------------------------------------------------------------

_SKIP_PATTERNS = re.compile(
    r"""^(
        pata\s*nahi | nahi\s*pata | pata\s*nahin | nahin\s*pata |
        don'?t\s*know | dont\s*know | no\s*idea | not\s*sure |
        skip | na | naa | \? | idk | hmm | huh |
        mujhe\s*nahi\s*pata | maloom\s*nahi | yaad\s*nahi |
        kya\s*pata | nahi\s*maloom
    )$""",
    re.VERBOSE | re.IGNORECASE,
)

def is_skip(text: str) -> bool:
    return bool(_SKIP_PATTERNS.match(text.strip()))


# ---------------------------------------------------------------------------
# Hinglish regex extractor (API-free)
# ---------------------------------------------------------------------------

def _extract_fields(text: str, current_profile: dict, last_question: Optional[str] = None) -> dict:
    """Extract profile fields from natural language. Returns only newly found fields."""
    t = text.lower().strip()
    extracted: dict = {}

    # ── Age ─────────────────────────────────────────────────────────────────
    # "meri umar 35 hai", "35 saal", "35 years old", "age 35"
    age_m = re.search(
        r'(?:umar|age|saal|years?|varsh|साल|उम्र)[^\d]*(\d{1,3})'
        r'|(\d{1,3})\s*(?:saal|years?\s*old|varsh|साल)',
        t
    )
    if age_m:
        age = int(age_m.group(1) or age_m.group(2))
        if 5 < age < 120:
            extracted["age"] = age
    elif last_question and re.search(r'umar|age', last_question, re.I):
        nums = re.findall(r'\b(\d{1,3})\b', t)
        if nums:
            age = int(nums[0])
            if 5 < age < 120:
                extracted["age"] = age

    # ── Income ───────────────────────────────────────────────────────────────
    # "3 lakh", "80 hazar", "1.5 lakh", "₹2,50,000"
    inc_m = re.search(r'(\d+(?:\.\d+)?)\s*(?:lakh|lacs?|lakhs?|लाख)', t)
    if inc_m:
        extracted["annual_income"] = int(float(inc_m.group(1)) * 100_000)
    else:
        inc_k = re.search(r'(\d+)\s*(?:hazaar|hazar|thousand|हज़ार|हजार|k\b)', t)
        if inc_k:
            extracted["annual_income"] = int(inc_k.group(1)) * 1_000
        elif last_question and re.search(r'income|amdani|saalana|कमाई', last_question, re.I):
            # Plain number in income question context
            raw = t.replace(',', '')
            nums = re.findall(r'\b(\d{4,8})\b', raw)
            if nums:
                extracted["annual_income"] = int(nums[0])

    # ── Family size ───────────────────────────────────────────────────────────
    fam_m = re.search(
        r'(\d+)\s*(?:log|member|pariwar|family|sadasya|jankar|जन|परिवार|angg)',
        t
    )
    if fam_m:
        n = int(fam_m.group(1))
        if 1 <= n <= 30:
            extracted["family_size"] = n
    elif last_question and re.search(r'family|ghar|pariwar|kitne', last_question, re.I):
        nums = re.findall(r'\b(\d{1,2})\b', t)
        if nums:
            n = int(nums[0])
            if 1 <= n <= 30:
                extracted["family_size"] = n

    # ── Gender ────────────────────────────────────────────────────────────────
    if re.search(r'\b(?:main\s+(?:ek\s+)?(?:aurat|mahila|lady|woman|beti|ladki)|female|महिला|औरत|beti|she\b|her\b)\b', t):
        extracted["gender"] = "F"
    elif re.search(r'\b(?:main\s+(?:ek\s+)?(?:aadmi|purush|mard|man|ladka)|male|पुरुष|आदमी|he\b|his\b|mr\.?)\b', t):
        extracted["gender"] = "M"
    elif 'transgender' in t or 'kinnar' in t or 'किन्नर' in t:
        extracted["gender"] = "Transgender"
    elif last_question and re.search(r'purush|gender|mahila|linga', last_question, re.I):
        if re.search(r'\b(?:mahila|female|f\b|aurat|lady|woman)\b', t):
            extracted["gender"] = "F"
        elif re.search(r'\b(?:purush|male|m\b|aadmi|mard|man)\b', t):
            extracted["gender"] = "M"

    # ── Urban/Rural ───────────────────────────────────────────────────────────
    if re.search(r'\b(?:gaon|village|gram|गाँव|गांव|rural|gramin|dehat|देहात)\b', t):
        extracted["is_urban"] = False
    elif re.search(r'\b(?:shehar|shahr|city|town|urban|शहर|नगर|metros?)\b', t):
        extracted["is_urban"] = True
    elif last_question and re.search(r'gaon|urban|shehar|village|rural', last_question, re.I):
        if re.search(r'\bgaon\b|village|rural|gram', t):
            extracted["is_urban"] = False
        elif re.search(r'\bshehar\b|city|town|urban', t):
            extracted["is_urban"] = True

    # ── State ────────────────────────────────────────────────────────────────
    STATE_MAP = {
        "Uttar Pradesh": r'\b(?:up\b|uttar\s*pradesh|u\.p\.)\b',
        "Bihar": r'\bbihar\b',
        "Rajasthan": r'\brajasthan\b',
        "Madhya Pradesh": r'\b(?:mp\b|madhya\s*pradesh|m\.p\.)\b',
        "Maharashtra": r'\bmaharashtra\b',
        "West Bengal": r'\b(?:west\s*bengal|bengal\b|wb\b)\b',
        "Gujarat": r'\bgujarat\b',
        "Odisha": r'\b(?:odisha|orissa)\b',
        "Karnataka": r'\bkarnataka\b',
        "Jharkhand": r'\bjharkhand\b',
        "Assam": r'\bassam\b',
        "Kerala": r'\bkerala\b',
        "Tamil Nadu": r'\b(?:tamil\s*nadu|tamilnadu|tn\b)\b',
        "Telangana": r'\btelangana\b',
        "Andhra Pradesh": r'\b(?:andhra|andhra\s*pradesh|ap\b)\b',
        "Punjab": r'\bpunjab\b',
        "Haryana": r'\bharyana\b',
        "Chhattisgarh": r'\b(?:chhattisgarh|chattisgarh)\b',
        "Uttarakhand": r'\b(?:uttarakhand|uttaranchal)\b',
        "Himachal Pradesh": r'\b(?:himachal|himachal\s*pradesh|hp\b)\b',
        "Delhi": r'\b(?:delhi|dilli|new\s*delhi)\b',
        "Jammu & Kashmir": r'\b(?:jammu|kashmir|j\s*&?\s*k)\b',
        "Goa": r'\bgoa\b',
        "Manipur": r'\bmanipuр\b',
        "Meghalaya": r'\bmeghalaya\b',
        "Tripura": r'\btripura\b',
    }
    for state, pat in STATE_MAP.items():
        if re.search(pat, t, re.I):
            extracted["state"] = state
            break

    # ── Caste category ────────────────────────────────────────────────────────
    if re.search(r'\b(?:sc\b|scheduled\s*caste|anusuchit\s*jati|dalit)\b', t):
        extracted["caste_category"] = "SC"
    elif re.search(r'\b(?:st\b|scheduled\s*tribe|anusuchit\s*janjati|tribal|adivasi|vanvasi)\b', t):
        extracted["caste_category"] = "ST"
    elif re.search(r'\b(?:obc\b|other\s*backward|pichda\s*varg|पिछड़ा|obc)\b', t):
        extracted["caste_category"] = "OBC"
    elif re.search(r'\b(?:general\b|gen\b|saamanye|सामान्य|unreserved|open\s*category)\b', t):
        extracted["caste_category"] = "General"
    elif last_question and re.search(r'category|caste|varg|jati', last_question, re.I):
        if 'sc' in t.split() or 'dalit' in t:
            extracted["caste_category"] = "SC"
        elif 'st' in t.split() or 'tribe' in t or 'adivasi' in t:
            extracted["caste_category"] = "ST"
        elif 'obc' in t.split() or 'pichda' in t:
            extracted["caste_category"] = "OBC"
        elif 'general' in t or 'gen' in t.split():
            extracted["caste_category"] = "General"

    # ── Occupation ───────────────────────────────────────────────────────────
    if re.search(r'\b(?:kisan|farmer|kheti|krishi|खेती|किसान|agriculture)\b', t):
        extracted["occupation"] = "Farmer"
    elif re.search(r'\b(?:majdoor|mazdoor|daily\s*wage|labourer|laborer|मजदूर|दिहाड़ी|dihari)\b', t):
        extracted["occupation"] = "Daily wage worker"
    elif re.search(r'\b(?:vendor|hawker|rehdi|pheri|feriwala|फेरीवाला|street\s*vendor|thela)\b', t):
        extracted["occupation"] = "street_vendor"
    elif re.search(r'\b(?:artisan|karigar|craftsman|कारीगर|shilpkar|carpenter|barber|weaver|potter|blacksmith)\b', t):
        extracted["occupation"] = "Artisan"
    elif re.search(r'\b(?:dukaan|shopkeeper|shop|dukaandar|दुकानदार|trader|vyapari)\b', t):
        extracted["occupation"] = "Shopkeeper"
    elif re.search(r'\b(?:student|padh|school|college|university|छात्र|पढ़|padhai)\b', t):
        extracted["occupation"] = "Student"
    elif re.search(r'\b(?:grahini|housewife|homemaker|घरेलू|गृहिणी|gharelu)\b', t):
        extracted["occupation"] = "Homemaker"
    elif re.search(r'\b(?:berozgaar|unemployed|naukri\s*nahi|job\s*nahi|बेरोज़गार|rojgar\s*nahi)\b', t):
        extracted["occupation"] = "Unemployed"
    elif re.search(r'\b(?:sarkari\s*naukri|govt\s*job|government\s*employee|sarkari\s*mulazim|IAS|IPS|IFS)\b', t):
        extracted["occupation"] = "Government employee"
        extracted["is_govt_employee"] = True
    elif re.search(r'\b(?:teacher|shikshak|master\b|adhyapak)\b', t):
        extracted["occupation"] = "Teacher"
    elif re.search(r'\b(?:driver|chauffeur|chalak|auto\s*driver|truck\s*driver|taxi)\b', t):
        extracted["occupation"] = "Driver"
    elif re.search(r'\b(?:nurse|doctor|physician|vaid|hakeem)\b', t):
        extracted["occupation"] = "Healthcare worker"

    # ── Boolean fields ────────────────────────────────────────────────────────
    def _bool_field(key_pattern: str, yes_pats: list[str], no_pats: list[str]) -> Optional[bool]:
        if not re.search(key_pattern, t, re.I):
            return None
        for np in no_pats:
            if re.search(np, t, re.I):
                return False
        for yp in yes_pats:
            if re.search(yp, t, re.I):
                return True
        return None

    YES = [r'\b(?:haan|yes|hai|h\b|y\b|bilkul|zaroor|confirmed|theek)\b']
    NO  = [r'\b(?:nahi|nahin|no\b|n\b|naa|mat|never|nope)\b']

    # Aadhaar
    if last_question and re.search(r'aadhaar|aadhar|adhar|आधार', last_question, re.I) and 'bank' not in last_question.lower():
        result = None
        for np in NO:
            if re.search(np, t): result = False
        if result is None:
            for yp in YES:
                if re.search(yp, t): result = True
        if result is not None:
            extracted["has_aadhaar"] = result
    elif re.search(r'\b(?:aadhaar|aadhar|adhar|आधार)\b', t):
        if re.search(r'\b(?:nahi|no\b|nahin)\b', t):
            extracted["has_aadhaar"] = False
        else:
            extracted["has_aadhaar"] = True

    # Bank account
    if last_question and re.search(r'bank\s*account|bank\s*khata|बैंक', last_question, re.I) and 'linked' not in last_question.lower():
        result = None
        for np in NO:
            if re.search(np, t): result = False
        if result is None:
            for yp in YES:
                if re.search(yp, t): result = True
        if result is not None:
            extracted["has_bank_account"] = result
    elif re.search(r'\bbank\s*(?:account|khata|khata)\b', t):
        if re.search(r'\b(?:nahi|no\b|nahin)\b', t):
            extracted["has_bank_account"] = False
        else:
            extracted["has_bank_account"] = True

    # Aadhaar-bank linking
    if last_question and re.search(r'linked|link\b|जोड़ा', last_question, re.I):
        result = None
        for np in NO:
            if re.search(np, t): result = False
        if result is None:
            for yp in YES:
                if re.search(yp, t): result = True
        if result is not None:
            extracted["is_aadhaar_linked"] = result
    elif re.search(r'aadhaar.*link|bank.*link|linked.*aadhaar', t):
        if re.search(r'\b(?:nahi|no\b|nahin)\b', t):
            extracted["is_aadhaar_linked"] = False
        else:
            extracted["is_aadhaar_linked"] = True

    # Land ownership
    if re.search(r'\b(?:zameen|land|khet|farm|plot|property)\b', t):
        if re.search(r'\b(?:apni|own|khud|meri|hamaari)\b', t):
            extracted["land_ownership"] = "owns"
        elif re.search(r'\b(?:kiraye|lease|rent|bhade)\b', t):
            extracted["land_ownership"] = "leases"
        elif re.search(r'\b(?:nahi|no|nahin|koi nahi)\b', t):
            extracted["land_ownership"] = "none"
    elif last_question and re.search(r'zameen|land', last_question, re.I):
        if re.search(r'\b(?:apni|own|khud|meri)\b', t):
            extracted["land_ownership"] = "owns"
        elif re.search(r'\b(?:kiraye|lease|rent|bhade)\b', t):
            extracted["land_ownership"] = "leases"
        elif re.search(r'\b(?:nahi|no|nahin)\b', t):
            extracted["land_ownership"] = "none"

    # Land area
    if re.search(r'\b(?:zameen|land|khet|bigha|acre|hectare|gaj)\b', t):
        nums = re.findall(r'[\d.]+', t.replace(',', ''))
        if nums:
            val = float(nums[0])
            if any(u in t for u in ("sqft", "sq ft", "square feet", "square foot")):
                extracted["land_area_hectares"] = normalize_sqft_to_hectares(val)
            elif any(u in t for u in ("gaj", "गज", "sq yard", "square yard")):
                extracted["land_area_hectares"] = normalize_gaj_to_hectares(val)
            elif any(u in t for u in ("acre", "एकड़")):
                extracted["land_area_hectares"] = round(val * 0.404686, 4)
            elif any(u in t for u in ("bigha", "बीघा")):
                extracted["land_area_hectares"] = normalize_bigha_to_hectares(val, current_profile.get("state", ""))
            elif any(u in t for u in ("hectare", "ha\b")):
                extracted["land_area_hectares"] = round(val, 4)

    # Marital status
    if re.search(r'\b(?:widow|vidhwa|vidhur|विधवा|विधुर|pati\s*guzar)\b', t):
        extracted["marital_status"] = "widowed"
    elif re.search(r'\b(?:shaadi|married|vivahit|विवाहित|shadi|wife|husband|pati|patni)\b', t):
        extracted["marital_status"] = "married"
    elif re.search(r'\b(?:unmarried|single|avivahit|अविवाहित|kuanra|kunwara|kunwari|bachelor)\b', t):
        extracted["marital_status"] = "unmarried"
    elif re.search(r'\b(?:divorced|talak|alag)\b', t):
        extracted["marital_status"] = "divorced"

    # LPG gas
    if re.search(r'\b(?:lpg|gas|cylinder|gasaha|ujjwala|गैस)\b', t):
        if re.search(r'\b(?:nahi|no\b|nahin)\b', t):
            extracted["has_lpg_connection"] = False
        else:
            extracted["has_lpg_connection"] = True

    # Ration card
    if re.search(r'\b(?:ration\s*card|rashan\s*card|राशन\s*कार्ड|bpl\s*card|pds)\b', t):
        if re.search(r'\b(?:nahi|no\b|nahin)\b', t):
            extracted["has_ration_card"] = "none"
        elif re.search(r'\b(?:aay|antyodaya)\b', t):
            extracted["has_ration_card"] = "AAY"
        else:
            extracted["has_ration_card"] = "PHH"

    # Disability
    if re.search(r'\b(?:disability|viklang|handicap|divyang|disabled|apahij|विकलांग|दिव्यांग)\b', t):
        pct_m = re.search(r'(\d+)\s*(?:percent|%)', t)
        if pct_m:
            pct = int(pct_m.group(1))
            extracted["disability_percent"] = pct
        elif re.search(r'\b(?:nahi|no\b|nahin)\b', t):
            extracted["disability_percent"] = 0
        else:
            extracted["disability_percent"] = 40   # minimum threshold

    # Pregnancy / lactating
    if re.search(r'\b(?:pregnant|garbhvati|गर्भवती|lactating|dhoodh\s*pila)\b', t):
        extracted["is_pregnant_or_lactating"] = True

    # Girl child under 10
    if re.search(r'\b(?:beti|girl|ladki|daughter)\b', t):
        if re.search(r'\b(?:choti|chhoti|small|young|nayi|baby|bachchi)\b', t) or re.search(r'\b[1-9]\b', t):
            extracted["has_girl_child_under_10"] = True

    # Govt employee
    if re.search(r'\b(?:sarkari|government|govt)\s*(?:naukri|job|employee|kaam)\b', t):
        extracted["is_govt_employee"] = True
    elif last_question and re.search(r'sarkari|govt.*employ', last_question, re.I):
        if re.search(r'\b(?:haan|yes|hai)\b', t):
            extracted["is_govt_employee"] = True
        elif re.search(r'\b(?:nahi|no|nahin)\b', t):
            extracted["is_govt_employee"] = False

    return extracted


# ---------------------------------------------------------------------------
# Contradiction handling
# ---------------------------------------------------------------------------

_CONTRADICTION_QUESTIONS = {
    ("state", "is_urban"): (
        "Aapne {state} mention kiya jo mainly rural area hai, lekin aapne shehar/city bola. "
        "Confirm karein — aap kisi town ya city mein rehte hain? (haan/nahi)"
    ),
    ("annual_income", "is_income_tax_payer"): (
        "Aapki income ₹{annual_income:,} hai jo tax threshold se kam hai, lekin aapne income tax bola. "
        "Kya aap ITR file karte hain? (haan/nahi)"
    ),
    ("annual_income", "is_govt_employee"): (
        "Aapki income ₹{annual_income:,}/year — government employees ki income usually zyada hoti hai. "
        "Kya yeh sahi hai? Please verify karein."
    ),
    ("has_bank_account", "is_aadhaar_linked"): (
        "Aapne bola bank account nahi hai, lekin Aadhaar linked bhi bola. "
        "Bank account ke bina Aadhaar link nahi hota. Kya aapka bank account hai? (haan/nahi)"
    ),
}


def _get_contradiction_question(contradiction, profile: dict) -> str:
    key = tuple(sorted(contradiction.fields))
    tmpl = _CONTRADICTION_QUESTIONS.get(key)
    if tmpl:
        try:
            return tmpl.format(**profile)
        except (KeyError, ValueError):
            pass
    return contradiction.description + " — " + contradiction.suggestion


# ---------------------------------------------------------------------------
# Question sequencer
# ---------------------------------------------------------------------------

# All follow-up questions — FIELD_PRIORITY covers mandatory + common optional;
# append only the remaining optional fields not already listed there.
_ALL_FIELD_QUESTIONS: list[tuple[str, str]] = FIELD_PRIORITY + [
    ("has_lpg_connection",       "क्या आपके घर में LPG गैस कनेक्शन है? · Ghar mein LPG gas hai?"),
    ("is_pregnant_or_lactating", "क्या घर में कोई महिला गर्भवती हैं? · Koi pregnant ya recently delivery hui?"),
]


def _next_question(profile: dict, skipped: set) -> Optional[tuple[str, str]]:
    """Return (field_name, question_text) for the highest-priority unanswered field, or None."""
    for field_name, question in _ALL_FIELD_QUESTIONS:
        if profile.get(field_name) is None and field_name not in skipped:
            return (field_name, question)
    return None


def _mandatory_filled(profile: dict, skipped: set) -> bool:
    """True if all mandatory fields are either filled or consciously skipped."""
    for f in MANDATORY_FIELDS:
        if profile.get(f) is None and f not in skipped:
            return False
    return True


def _count_filled(profile: dict) -> int:
    return sum(1 for v in profile.values() if v is not None)


# ---------------------------------------------------------------------------
# Reply builder (Hinglish, warm tone)
# ---------------------------------------------------------------------------

_OPENING = (
    "Namaste! 🙏 Apni situation batayein — kahan rehte hain, kya kaam karte hain, "
    "income kitni hai, parivaar mein kitne log hain.\n\n"
    "<span style='opacity:0.8'>नमस्ते! अपने बारे में बताइए — कहाँ रहते हैं, क्या काम करते हैं, "
    "आमदनी कितनी है।</span>\n\n"
    "<em>Hindi, English, ya Hinglish — jaise comfortable ho. 'Skip' ya 'pata nahi' type karein "
    "agar koi cheez nahi pata.</em>"
)

def _format_field_value(field_name: str, value) -> str:
    """Human-readable value for a profile field."""
    if isinstance(value, bool):
        return "Haan ✓" if value else "Nahi ✗"
    if field_name == "annual_income" and isinstance(value, int):
        if value >= 100_000:
            return f"₹{value/100_000:.1f}L/yr"
        return f"₹{value:,}/yr"
    if field_name == "is_urban":
        return "Shehar" if value else "Gaon"
    return str(value)


def _build_reply(
    text: str,
    extracted: dict,
    contradictions: list,
    state: ConversationState,
) -> str:
    parts = []

    # Acknowledgement of what we got
    if extracted:
        ack_items = []
        for k, v in extracted.items():
            label = _FIELD_LABELS.get(k, k.replace("_", " ").title())
            ack_items.append(f"{label}: <strong>{_format_field_value(k, v)}</strong>")
        parts.append("✓ Samajh gaya: " + " · ".join(ack_items))
    elif is_skip(text):
        if state.last_question_field:
            state.skipped.add(state.last_question_field)
        parts.append("Theek hai, koi baat nahi! Agli baat poochta hoon.")
    else:
        parts.append(
            "Yeh clearly nahi samajh aaya — try karein: "
            "<em>\"main 35 saal ka kisan hoon UP se, income 80 hazar\"</em>"
        )

    # Surface contradictions
    for c in contradictions:
        key = tuple(sorted(c.fields))
        if key not in [tuple(sorted(x)) for x in state.contradictions_seen]:
            state.contradictions_seen.append(list(c.fields))
            q = _get_contradiction_question(c, {**state.profile, **extracted})
            parts.append(f"⚠️ <strong>Contradiction:</strong> {q}")
            # Clear last_question_field so a "pata nahi" on a contradiction
            # question does not accidentally skip an unrelated profile field.
            state.last_question_field = None
            state.last_question = None
            return "<br><br>".join(parts)   # pause here for clarification

    # Next question or done
    merged = {**state.profile, **extracted}
    next_q = _next_question(merged, state.skipped)

    if next_q is None or _mandatory_filled(merged, state.skipped):
        if _count_filled(merged) >= 5:
            parts.append(
                "🎉 Kaafi jankari aa gayi! Niche <strong>Nataije Dekho</strong> button dabayein. "
                "Ya main aur poochhta hoon agar kuch baaki hai."
            )
            state.done = True
        else:
            parts.append("Kuch aur batayein apne baare mein — income, parivaar, ya koi bhi yojana ke baare mein?")
    else:
        field_name, question = next_q
        state.last_question = question
        state.last_question_field = field_name
        parts.append(question)

    return "<br><br>".join(parts)


_FIELD_LABELS = {
    "age": "Age · उम्र",
    "gender": "Gender · लिंग",
    "state": "State · राज्य",
    "is_urban": "Location · स्थान",
    "caste_category": "Category · वर्ग",
    "annual_income": "Income · आमदनी",
    "occupation": "Occupation · पेशा",
    "family_size": "Family · परिवार",
    "has_aadhaar": "Aadhaar",
    "has_bank_account": "Bank Account · बैंक",
    "is_aadhaar_linked": "Aadhaar-Bank Link",
    "land_ownership": "Land · ज़मीन",
    "land_area_hectares": "Land Area",
    "marital_status": "Marital status · वैवाहिक",
    "has_ration_card": "Ration Card · राशन कार्ड",
    "disability_percent": "Disability · विकलांगता",
    "has_lpg_connection": "LPG Gas",
    "is_pregnant_or_lactating": "Pregnancy",
    "is_govt_employee": "Govt Employee",
}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def process_turn(text: str, state: ConversationState) -> tuple[str, dict]:
    """Process one conversational turn. Returns (reply_html, newly_extracted_fields)."""
    text = text.strip()[:600]

    if not text:
        return "Kuch toh likho! Apni situation batao.", {}

    # Skip / don't know
    if is_skip(text):
        if state.last_question_field:
            state.skipped.add(state.last_question_field)
        # Find next question
        next_q = _next_question(state.profile, state.skipped)
        if next_q:
            field_name, question = next_q
            state.last_question = question
            state.last_question_field = field_name
            reply = f"Theek hai! {question}"
        elif _count_filled(state.profile) >= 4:
            # Only declare done if we actually have enough data
            state.done = True
            reply = "🎉 Enough info aa gayi! Niche <strong>Nataije Dekho</strong> dabayein."
        else:
            # No more questions but not enough data — prompt for free-form input
            reply = (
                "Kuch aur batayein apne baare mein — "
                "income, parivaar size, ya koi bhi yojana ke baare mein?"
            )
        state.turn += 1
        return reply, {}

    # Extract fields
    extracted = _extract_fields(text, state.profile, state.last_question)

    # Update profile
    for k, v in extracted.items():
        if v is not None:
            state.profile[k] = v

    # Detect contradictions
    contradictions = detect_contradictions(state.profile)

    # Build reply
    reply = _build_reply(text, extracted, contradictions, state)

    state.turn += 1
    return reply, extracted


def get_opening_message() -> str:
    return _OPENING
