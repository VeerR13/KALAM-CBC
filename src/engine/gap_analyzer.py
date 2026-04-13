"""Generates gap analysis from a MatchResult."""
from src.models.match_result import GapItem, MatchResult
from src.models.scheme import RuleResult
from src.engine.confidence import MatchStatus


class GapAnalyzer:
    """Identifies what's blocking or uncertain about eligibility."""

    @staticmethod
    def analyze(result: MatchResult) -> list[GapItem]:
        """Return list of gaps for LIKELY_ELIGIBLE and AMBIGUOUS results. Empty for ELIGIBLE/INELIGIBLE."""
        if result.status in (MatchStatus.ELIGIBLE, MatchStatus.INELIGIBLE):
            return []

        gaps = []
        for eval_ in result.rule_evaluations:
            if eval_.result == RuleResult.MISSING:
                gaps.append(GapItem(
                    gap_type="MISSING_INPUT",
                    description=f"Missing data: {eval_.explanation}",
                    action="Provide this information to get an accurate eligibility assessment.",
                ))
            elif eval_.result == RuleResult.AMBIGUOUS:
                gaps.append(GapItem(
                    gap_type="AMBIGUOUS_CRITERION",
                    description=f"Eligibility unclear: {eval_.explanation}",
                    action="Contact the local government office or CSC for clarification.",
                ))

        for prereq_id in result.prerequisite_scheme_ids:
            gaps.append(GapItem(
                gap_type="MISSING_PREREQUISITE",
                description=f"Scheme '{prereq_id}' must be enrolled in first.",
                action=f"Apply for {prereq_id} before this scheme.",
            ))

        return gaps
