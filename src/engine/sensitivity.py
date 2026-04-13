"""Sensitivity analysis — re-runs engine with profile variations to detect fragile results."""
from dataclasses import dataclass
from typing import Optional

from src.engine.confidence import ConfidenceScorer, MatchStatus
from src.engine.rule_engine import evaluate_scheme
from src.loader import load_all_schemes
from src.models.scheme import Scheme
from src.models.user_profile import UserProfile

# Known scheme thresholds that produce eligibility boundaries
_INCOME_THRESHOLDS = [
    (100000,  "NFSA/PM-JAY income ceiling"),
    (180000,  "PM-SYM limit (₹15,000/month × 12)"),
    (250000,  "income tax filing threshold"),
    (300000,  "PMAY-U EWS ceiling"),
    (600000,  "PMAY-U LIG ceiling"),
    (900000,  "PMAY-U MIG ceiling"),
]

_AGE_THRESHOLDS = [18, 40, 59, 60, 80]


@dataclass
class SensitivityFlag:
    scheme_id: str
    scheme_name: str
    field_changed: str
    original_value: object
    test_value: object
    original_status: MatchStatus
    new_status: MatchStatus
    message: str
    is_opportunity: bool   # True = change would help
    proximity_note: str    # e.g. "₹15,000 away from threshold"


def _parse_schemes() -> dict[str, Scheme]:
    return {s["scheme_id"]: Scheme(**s) for s in load_all_schemes()}


def _evaluate(profile: UserProfile, schemes: dict[str, Scheme]) -> dict[str, MatchStatus]:
    results = {}
    for sid, scheme in schemes.items():
        rr = evaluate_scheme(scheme, profile)
        _, status = ConfidenceScorer.score(scheme, rr)
        results[sid] = status
    return results


def _fmt_field(field: str, value) -> str:
    if field == "annual_income":
        return f"₹{int(value):,}/year"
    if field == "age":
        return f"age {value}"
    if field == "disability_percent":
        return f"{value}% disability"
    return str(value)


class SensitivityAnalyzer:
    """
    Re-runs the rule engine with modified profiles to detect fragile eligibility.
    Nothing is hardcoded — every flag is produced by an actual engine run.
    """

    def analyze(self, profile: UserProfile, original_statuses: dict[str, MatchStatus]) -> list[SensitivityFlag]:
        schemes = _parse_schemes()
        flags: list[SensitivityFlag] = []
        seen: set[tuple] = set()

        variations = self._build_variations(profile)

        for field_name, test_cases in variations.items():
            for test_value, proximity_note in test_cases:
                try:
                    modified = profile.model_copy(update={field_name: test_value})
                except Exception:
                    continue

                new_statuses = _evaluate(modified, schemes)

                for sid, scheme in schemes.items():
                    orig = original_statuses.get(sid)
                    new = new_statuses.get(sid)
                    if orig is None or new is None or orig == new:
                        continue

                    key = (sid, field_name, str(test_value))
                    if key in seen:
                        continue
                    seen.add(key)

                    orig_val = getattr(profile, field_name)
                    is_opportunity = self._is_better(new, orig)
                    msg = self._message(
                        scheme.name, field_name, orig_val, test_value, orig, new
                    )

                    flags.append(SensitivityFlag(
                        scheme_id=sid,
                        scheme_name=scheme.name,
                        field_changed=field_name,
                        original_value=orig_val,
                        test_value=test_value,
                        original_status=orig,
                        new_status=new,
                        message=msg,
                        is_opportunity=is_opportunity,
                        proximity_note=proximity_note,
                    ))

        # Sort: warnings first (is_opportunity=False), then opportunities
        flags.sort(key=lambda f: (f.is_opportunity, f.scheme_name))
        return flags

    def _build_variations(self, profile: UserProfile) -> dict[str, list[tuple]]:
        variations: dict[str, list[tuple]] = {}

        # ── Income ───────────────────────────────────────────────────────────
        if profile.annual_income is not None:
            inc = profile.annual_income
            cases = []
            for threshold, label in _INCOME_THRESHOLDS:
                diff = abs(threshold - inc)
                if diff == 0:
                    continue
                if diff <= 50000:
                    direction = "rises" if threshold > inc else "drops"
                    cases.append((threshold, f"income {direction} by ₹{diff:,} to ₹{threshold:,} ({label})"))
            # ±10%
            cases.append((int(inc * 0.9), f"income drops 10% (₹{int(inc*0.1):,})"))
            cases.append((int(inc * 1.1), f"income rises 10% (₹{int(inc*0.1):,})"))
            if cases:
                variations["annual_income"] = cases

        # ── Age ──────────────────────────────────────────────────────────────
        if profile.age is not None:
            age = profile.age
            cases = []
            for threshold in _AGE_THRESHOLDS:
                diff = abs(threshold - age)
                if diff == 0:
                    continue
                if diff <= 3:
                    cases.append((threshold, f"{diff} year{'s' if diff > 1 else ''} from age {threshold} threshold"))
            if cases:
                variations["age"] = cases

        # ── Disability ───────────────────────────────────────────────────────
        if profile.disability_percent is not None and 0 < profile.disability_percent < 80:
            variations["disability_percent"] = [
                (80, "if disability certificate upgraded to 80%+")
            ]

        return variations

    @staticmethod
    def _is_better(new_status: MatchStatus, old_status: MatchStatus) -> bool:
        order = {
            MatchStatus.ELIGIBLE: 0,
            MatchStatus.LIKELY_ELIGIBLE: 1,
            MatchStatus.AMBIGUOUS: 2,
            MatchStatus.INSUFFICIENT_DATA: 3,
            MatchStatus.INELIGIBLE: 4,
        }
        return order.get(new_status, 9) < order.get(old_status, 9)

    def _message(self, scheme_name, field, old_val, new_val, old_status, new_status) -> str:
        old_fmt = _fmt_field(field, old_val)
        new_fmt = _fmt_field(field, new_val)
        if self._is_better(new_status, old_status):
            return (
                f"💡 {scheme_name}: currently {old_status.value.replace('_', ' ').lower()} "
                f"({old_fmt}). If {field.replace('_', ' ')} becomes {new_fmt}, "
                f"you could become {new_status.value.replace('_', ' ').lower()}."
            )
        return (
            f"⚠️ {scheme_name}: currently {old_status.value.replace('_', ' ').lower()} "
            f"({old_fmt}). If {field.replace('_', ' ')} changes to {new_fmt}, "
            f"this drops to {new_status.value.replace('_', ' ').lower()}."
        )
