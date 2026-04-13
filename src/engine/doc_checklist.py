"""Generates prioritized document checklist for eligible/likely schemes."""
from src.models.match_result import MatchResult
from src.engine.confidence import MatchStatus


class DocumentChecklistGenerator:
    """Produces a sorted document list for the user to collect."""

    @staticmethod
    def generate(result: MatchResult) -> list[dict]:
        """Return documents sorted by priority (lowest number first = fastest/easiest). Empty for INELIGIBLE."""
        if result.status == MatchStatus.INELIGIBLE:
            return []
        return sorted(result.required_documents, key=lambda d: d.get("priority", 99))
