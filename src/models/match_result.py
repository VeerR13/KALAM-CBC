"""MatchResult and GapAnalysis output models."""
from typing import Optional
from pydantic import BaseModel
from src.engine.confidence import MatchStatus
from src.models.scheme import RuleResult


class RuleEvaluation(BaseModel):
    rule_id: str
    result: RuleResult
    explanation: str
    is_mandatory: bool
    weight: int


class GapItem(BaseModel):
    gap_type: str  # MISSING_DOCUMENT|MISSING_PREREQUISITE|AMBIGUOUS_CRITERION|MISSING_INPUT
    description: str
    action: str


class MatchResult(BaseModel):
    scheme_id: str
    scheme_name: str
    status: MatchStatus
    confidence: float
    rule_evaluations: list[RuleEvaluation]
    gaps: list[GapItem] = []
    prerequisite_scheme_ids: list[str] = []
    required_documents: list[dict] = []
    benefit_summary: str = ""
