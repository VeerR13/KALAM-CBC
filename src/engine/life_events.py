"""Life event projector — advances user's age and re-runs engine to surface upcoming changes."""
from dataclasses import dataclass, field
from typing import Optional

from src.engine.confidence import ConfidenceScorer, MatchStatus
from src.engine.rule_engine import evaluate_scheme
from src.loader import load_all_schemes
from src.models.scheme import Scheme
from src.models.user_profile import UserProfile


@dataclass
class LifeEvent:
    years_ahead: Optional[int]      # None = timing unknown
    future_age: Optional[int]
    scheme_id: str
    scheme_name: str
    scheme_icon: str
    current_status: MatchStatus
    future_status: MatchStatus
    is_opportunity: bool    # future is better
    is_deadline: bool       # future is worse — act NOW
    note: str = ""


_ICONS = {
    "apy": "📊", "pm_sym": "👷", "nsap_ignoaps": "👴",
    "nsap_ignwps": "👩", "nsap_igndps": "♿",
    "sukanya_samriddhi": "👧", "ayushman_bharat": "🏥",
}

_STATUS_ORDER = {
    MatchStatus.ELIGIBLE: 0,
    MatchStatus.LIKELY_ELIGIBLE: 1,
    MatchStatus.AMBIGUOUS: 2,
    MatchStatus.INSUFFICIENT_DATA: 3,
    MatchStatus.INELIGIBLE: 4,
}


def _is_better(a: MatchStatus, b: MatchStatus) -> bool:
    return _STATUS_ORDER.get(a, 9) < _STATUS_ORDER.get(b, 9)


class LifeEventProjector:
    """
    NOT a pre-built list. Actually creates future profiles and runs the engine on them.
    """

    def project(
        self,
        profile: UserProfile,
        current_statuses: dict[str, MatchStatus],
    ) -> list[LifeEvent]:
        if profile.age is None:
            return []

        schemes = {s["scheme_id"]: Scheme(**s) for s in load_all_schemes()}
        events: list[LifeEvent] = []
        seen: set[tuple] = set()

        for years_ahead in [1, 2, 5, max(0, 60 - profile.age)]:
            if years_ahead <= 0:
                continue
            future_age = profile.age + years_ahead
            future_profile = profile.model_copy(update={"age": future_age})

            for sid, scheme in schemes.items():
                current = current_statuses.get(sid)
                if current is None:
                    continue

                rr = evaluate_scheme(scheme, future_profile)
                _, future_status = ConfidenceScorer.score(scheme, rr)

                if current == future_status:
                    continue

                key = (sid, years_ahead)
                if key in seen:
                    continue
                seen.add(key)

                is_better = _is_better(future_status, current)
                is_worse = _is_better(current, future_status)

                note = ""
                if sid in ("apy", "pm_sym") and is_worse:
                    note = f"Enrollment closes at age 40. You have {max(0, 40 - profile.age)} year(s) left to join."
                elif sid == "nsap_ignoaps" and is_better:
                    note = "Old age pension becomes available at 60."
                elif sid == "nsap_ignwps" and is_better:
                    note = "Widow pension becomes available at 40."

                events.append(LifeEvent(
                    years_ahead=years_ahead,
                    future_age=future_age,
                    scheme_id=sid,
                    scheme_name=scheme.name,
                    scheme_icon=_ICONS.get(sid, "📋"),
                    current_status=current,
                    future_status=future_status,
                    is_opportunity=is_better,
                    is_deadline=is_worse,
                    note=note,
                ))

        # Child age events
        events.extend(self._child_age_events(profile, current_statuses, schemes))

        # Sort: deadlines first (urgent), then opportunities
        events.sort(key=lambda e: (
            not e.is_deadline,
            e.years_ahead if e.years_ahead is not None else 999,
        ))
        return events

    def _child_age_events(
        self,
        profile: UserProfile,
        current_statuses: dict[str, MatchStatus],
        schemes: dict[str, Scheme],
    ) -> list[LifeEvent]:
        events = []
        sid = "sukanya_samriddhi"
        if profile.has_girl_child_under_10 and sid in current_statuses:
            current = current_statuses[sid]
            if current in (MatchStatus.ELIGIBLE, MatchStatus.LIKELY_ELIGIBLE):
                events.append(LifeEvent(
                    years_ahead=None,
                    future_age=None,
                    scheme_id=sid,
                    scheme_name="Sukanya Samriddhi Yojana",
                    scheme_icon="👧",
                    current_status=current,
                    future_status=MatchStatus.INELIGIBLE,
                    is_opportunity=False,
                    is_deadline=True,
                    note="Your daughter is under 10 now. Account must be opened before she turns 10 — after that this option is permanently closed.",
                ))
        return events
