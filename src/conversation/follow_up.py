"""Determines which missing fields to ask about first — prioritised by scheme coverage."""
from src.models.user_profile import UserProfile

# Fields ordered by number of schemes they affect (most impactful first)
FIELD_PRIORITY: list[tuple[str, str]] = [
    ("has_aadhaar", "Kya aapke paas Aadhaar card hai? (Do you have an Aadhaar card?)"),
    ("has_bank_account", "Kya aapka bank account hai? (Do you have a bank account?)"),
    ("is_urban", "Aap gaon mein rehte hain ya shehar mein? (Do you live in a village or city?)"),
    ("state", "Aap kis state mein rehte hain? (Which state do you live in?)"),
    ("annual_income", "Aapki saalana income kitni hai (approx)? (What is your annual income approx?)"),
    ("caste_category", "Aapki category kya hai — General, OBC, SC, ya ST?"),
    ("gender", "Aap purush hain, mahila hain, ya transgender? (Male, Female, or Transgender?)"),
    ("occupation", "Aap kya kaam karte hain? (What is your occupation?)"),
    ("family_size", "Aapke ghar mein kitne log hain? (How many people in your family?)"),
    ("is_aadhaar_linked", "Kya aapka Aadhaar bank account se linked hai?"),
    ("land_ownership", "Kya aapke paas zameen hai? Apni, kiraye ki, ya koi nahi?"),
    ("marital_status", "Aap shaadi-shuda hain? (What is your marital status?)"),
    ("has_ration_card", "Kya aapke paas ration card hai? (AAY/PHH/none?)"),
    ("disability_percent", "Kya aapko koi disability hai? Kitne percent?"),
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
