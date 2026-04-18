"""Determines which missing fields to ask about first — prioritised by scheme coverage."""
from src.models.user_profile import UserProfile

# Fields ordered by number of schemes they affect (most impactful first)
FIELD_PRIORITY: list[tuple[str, str]] = [
    ("has_aadhaar",      "क्या आपके पास आधार कार्ड है? · Kya aapke paas Aadhaar card hai?"),
    ("has_bank_account", "क्या आपका बैंक अकाउंट है? · Kya aapka bank account hai?"),
    ("is_urban",         "आप गाँव में रहते हैं या शहर में? · Gaon ya shehar?"),
    ("state",            "आप किस राज्य में रहते हैं? · Aap kis state mein rehte hain?"),
    ("annual_income",    "आपकी सालाना आमदनी कितनी है? · Saalana income kitni hai?"),
    ("caste_category",   "आपकी श्रेणी क्या है — General, OBC, SC, या ST? · Category kya hai?"),
    ("gender",           "आप पुरुष हैं, महिला हैं, या ट्रांसजेंडर? · Purush, mahila, ya transgender?"),
    ("occupation",       "आप क्या काम करते हैं? · Kya kaam karte hain?"),
    ("family_size",      "आपके घर में कितने लोग हैं? · Ghar mein kitne log hain?"),
    ("is_aadhaar_linked","क्या आपका आधार बैंक से जुड़ा है? · Aadhaar bank se linked hai?"),
    ("land_ownership",   "क्या आपके पास ज़मीन है? · Zameen hai aapke paas?"),
    ("marital_status",   "आप विवाहित हैं? · Shaadi-shuda hain?"),
    ("has_ration_card",  "क्या आपके पास राशन कार्ड है? · Ration card hai?"),
    ("disability_percent","क्या आपको कोई विकलांगता है? · Koi disability hai?"),
]

MANDATORY_FIELDS = {
    "age", "state", "is_urban", "caste_category", "gender",
    "annual_income", "occupation", "family_size",
    "has_bank_account", "has_aadhaar", "is_aadhaar_linked",
}


def get_next_question(profile_data: dict) -> str | None:
    """Return the highest-priority follow-up question for a missing mandatory field. None if all present."""
    for field, question in FIELD_PRIORITY:
        if field in MANDATORY_FIELDS and profile_data.get(field) is None:
            return question
    return None


def missing_mandatory_fields(profile_data: dict) -> list[str]:
    """Return list of mandatory fields not yet provided."""
    return [f for f in MANDATORY_FIELDS if profile_data.get(f) is None]
