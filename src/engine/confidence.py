"""Confidence scorer: aggregates per-rule results into scheme-level score and status."""
from enum import Enum
from src.models.scheme import Scheme, RuleResult


class MatchStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    LIKELY_ELIGIBLE = "LIKELY_ELIGIBLE"
    AMBIGUOUS = "AMBIGUOUS"
    INELIGIBLE = "INELIGIBLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ConfidenceScorer:
    """Computes confidence score and match status for a scheme evaluation.

    Algorithm: Pignistic probability (Smets & Kennes, 1994 — Transferable Belief Model)
    with Bayesian shrinkage toward the uniform prior for incomplete data coverage.

    Step 1 — Pignistic transform over evaluated rules:
        raw_score = (Σ w[PASS] + 0.5 · Σ w[AMBIGUOUS]) / Σ w[evaluated]

    The 0.5 coefficient is the rational betting rate under uncertainty: ambiguous
    belief mass is split evenly between eligible and ineligible (maximum entropy).

    Step 2 — Coverage-adjusted confidence:
        coverage  = Σ w[evaluated] / Σ w[all rules]
        confidence = (0.5 + (raw_score − 0.5) · coverage) × 100

    At coverage = 1.0, this reduces to raw_score × 100 (no shrinkage).
    At coverage < 1.0, the score shrinks toward 50% (maximum uncertainty prior):
    a scheme where only half the criteria were answerable cannot be 100% confident.
    This is equivalent to Bayesian updating with a Beta(1,1) uniform prior.

    Priority gates (before confidence thresholds):
      1. Mandatory FAIL         → INELIGIBLE (0 %)
      2. Mandatory AMBIGUOUS    → AMBIGUOUS  (coverage-adjusted score)
      3. Missing mandatory rule → INSUFFICIENT_DATA (0 %)
      4. Score-based: ≥90 ELIGIBLE · ≥70 LIKELY_ELIGIBLE · ≥40 AMBIGUOUS · else INELIGIBLE
    """

    @staticmethod
    def score(scheme: Scheme, rule_results: list[tuple[str, RuleResult, str]]) -> tuple[float, MatchStatus]:
        rule_map = {r.rule_id: r for r in scheme.rules}
        total_weight = sum(r.weight for r in scheme.rules)

        sum_passed = 0.0
        sum_ambiguous = 0.0
        sum_evaluated = 0.0
        has_mandatory_fail = False
        has_mandatory_ambiguous = False
        has_missing_mandatory = False

        for rule_id, result, _ in rule_results:
            rule = rule_map.get(rule_id)
            if rule is None:
                continue
            if result == RuleResult.MISSING:
                if rule.is_mandatory:
                    has_missing_mandatory = True
                continue  # MISSING excluded from pignistic numerator/denominator
            sum_evaluated += rule.weight
            if result == RuleResult.PASS:
                sum_passed += rule.weight
            elif result == RuleResult.AMBIGUOUS:
                sum_ambiguous += rule.weight
                if rule.is_mandatory:
                    has_mandatory_ambiguous = True
            elif result == RuleResult.FAIL:
                if rule.is_mandatory:
                    has_mandatory_fail = True

        def _confidence() -> float:
            """Pignistic probability with coverage-based Bayesian shrinkage."""
            if sum_evaluated == 0:
                return 0.0
            raw = (sum_passed + 0.5 * sum_ambiguous) / sum_evaluated
            coverage = sum_evaluated / total_weight if total_weight > 0 else 0.0
            return (0.5 + (raw - 0.5) * coverage) * 100

        # 1. Mandatory FAIL → definitively ineligible
        if has_mandatory_fail:
            return 0.0, MatchStatus.INELIGIBLE

        # 2. Mandatory AMBIGUOUS → flag ambiguity (more informative than "need info")
        if has_mandatory_ambiguous:
            return _confidence(), MatchStatus.AMBIGUOUS

        # 3. No rules evaluated or a mandatory rule is unanswered → genuinely unknown
        if sum_evaluated == 0 or has_missing_mandatory:
            return 0.0, MatchStatus.INSUFFICIENT_DATA

        # 4. Enough data — score normally
        confidence = _confidence()

        if confidence >= 90:
            return confidence, MatchStatus.ELIGIBLE
        elif confidence >= 70:
            return confidence, MatchStatus.LIKELY_ELIGIBLE
        elif confidence >= 40:
            return confidence, MatchStatus.AMBIGUOUS
        else:
            return confidence, MatchStatus.INELIGIBLE
