"""Scheme interaction detection — finds when taking one scheme affects another."""
from dataclasses import dataclass, field
from typing import Optional

from src.engine.confidence import MatchStatus


@dataclass
class Interaction:
    trigger_scheme: str
    affected_schemes: list[str]
    interaction_type: str   # mutual_exclusion_5yr | threshold_risk | prerequisite_enabler | proof_enabler
    title: str
    description: str
    severity: str           # warning | info | choice
    recommendation: Optional[str] = None


# Static interaction definitions
_INTERACTIONS: list[dict] = [
    {
        "trigger": "pmjdy",
        "affected": ["pm_kisan", "ujjwala", "pm_sym", "apy", "pmmvy",
                     "nsap_ignoaps", "nsap_ignwps", "nsap_igndps"],
        "type": "prerequisite_enabler",
        "title": "Bank account unlocks 8 other schemes",
        "description": "Opening a PMJDY bank account is Step 1. Almost every other scheme "
                       "needs a bank account for Direct Benefit Transfer (DBT).",
        "severity": "info",
        "recommendation": "Apply for PMJDY first — takes 1 day at any bank branch.",
    },
    {
        "trigger": "nfsa",
        "affected": ["ujjwala", "ayushman_bharat", "pmmvy"],
        "type": "proof_enabler",
        "title": "Ration card proves eligibility for 3 more schemes",
        "description": "A PHH or AAY ration card acts as proof of eligibility for "
                       "Ujjwala, Ayushman Bharat (PM-JAY), and PMMVY.",
        "severity": "info",
        "recommendation": "Apply for NFSA ration card early — it unlocks Ujjwala and Ayushman Bharat.",
    },
    {
        "trigger": "pmegp",
        "affected": ["pm_vishwakarma"],
        "type": "mutual_exclusion_5yr",
        "title": "PMEGP blocks PM Vishwakarma for 5 years",
        "description": "If you take a PMEGP subsidy, you cannot get PM Vishwakarma "
                       "for 5 years (and vice versa).",
        "severity": "choice",
        "recommendation": None,  # set dynamically
    },
    {
        "trigger": "pm_svanidhi",
        "affected": ["pm_vishwakarma"],
        "type": "mutual_exclusion_5yr",
        "title": "SVANidhi loan blocks PM Vishwakarma for 5 years",
        "description": "Taking a PM SVANidhi loan means you cannot get PM Vishwakarma "
                       "for 5 years.",
        "severity": "warning",
        "recommendation": "If you are a traditional artisan, consider Vishwakarma first "
                          "(₹3 lakh at 5% + tools + training). SVANidhi is better for "
                          "street vendors who need quick working capital.",
    },
    {
        "trigger": "pm_mudra",
        "affected": ["pm_vishwakarma"],
        "type": "mutual_exclusion_5yr",
        "title": "MUDRA loan blocks PM Vishwakarma for 5 years",
        "description": "Taking a MUDRA loan means you cannot get PM Vishwakarma for 5 years.",
        "severity": "choice",
        "recommendation": None,  # set dynamically
    },
    {
        "trigger": "pm_vishwakarma",
        "affected": ["pmegp", "pm_svanidhi", "pm_mudra"],
        "type": "mutual_exclusion_5yr",
        "title": "PM Vishwakarma blocks PMEGP / MUDRA / SVANidhi for 5 years",
        "description": "Taking PM Vishwakarma means you cannot use PMEGP, MUDRA, or "
                       "SVANidhi for 5 years.",
        "severity": "choice",
        "recommendation": None,  # set dynamically
    },
    {
        "trigger": "nsap_ignoaps",
        "affected": ["pm_kisan"],
        "type": "threshold_risk",
        "title": "High pension may affect PM-KISAN eligibility",
        "description": "PM-KISAN excludes pensioners receiving ≥₹10,000/month. "
                       "The ₹200–500 central NSAP pension is unlikely to hit this, but "
                       "if your state adds a large top-up (e.g. Delhi +₹2,000, "
                       "Kerala +₹1,600), check your total pension before applying.",
        "severity": "warning",
        "recommendation": "Apply for PM-KISAN now — current pension is well under ₹10,000/month. "
                          "Re-check if your state pension increases significantly.",
    },
]


def _is_active(scheme_id: str, eligible_ids: set[str]) -> bool:
    return scheme_id in eligible_ids


class InteractionDetector:
    """Detect scheme interactions given a set of eligible/likely-eligible scheme IDs."""

    def detect(self, eligible_ids: list[str]) -> list[Interaction]:
        """Return a list of relevant interactions for the given eligible scheme set."""
        active = set(eligible_ids)
        results: list[Interaction] = []

        for defn in _INTERACTIONS:
            trigger = defn["trigger"]
            affected = [s for s in defn["affected"] if _is_active(s, active)]

            # Only surface if trigger is eligible AND at least one affected scheme is also eligible
            if not _is_active(trigger, active) or not affected:
                continue

            # Build dynamic recommendation for mutual exclusion choices
            rec = defn.get("recommendation")
            if defn["type"] == "mutual_exclusion_5yr" and rec is None:
                if trigger in ("pmegp", "pm_mudra") and "pm_vishwakarma" in affected:
                    rec = (
                        "You qualify for both paths. "
                        "PM Vishwakarma: ₹3 lakh at 5% + ₹15,000 tools + training — "
                        "best for traditional crafts. "
                        "MUDRA: up to ₹20 lakh in stages — best if you want to scale. "
                        "PMEGP: 15–35% free subsidy on project cost — best for manufacturing. "
                        "Pick ONE path for the next 5 years."
                    )
                elif trigger == "pm_vishwakarma":
                    rec = (
                        "You qualify for Vishwakarma AND business loans. "
                        "Vishwakarma gives you 5% interest + tools + training. "
                        "MUDRA/PMEGP let you scale higher later. Pick ONE for next 5 years."
                    )

            results.append(Interaction(
                trigger_scheme=trigger,
                affected_schemes=affected,
                interaction_type=defn["type"],
                title=defn["title"],
                description=defn["description"],
                severity=defn["severity"],
                recommendation=rec,
            ))

        return results
