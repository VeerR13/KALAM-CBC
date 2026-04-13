"""Data models for schemes, rules, and rule evaluation results."""
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel


class RuleResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    AMBIGUOUS = "AMBIGUOUS"
    MISSING = "MISSING"


class RuleCondition(BaseModel):
    type: str  # field_check|exclusion|range_check|boolean_check|composite|state_dependent
    field: Optional[str] = None
    operator: Optional[str] = None
    values: Optional[list[Any]] = None
    ambiguous_values: Optional[list[Any]] = None
    equals: Optional[Any] = None
    min: Optional[float] = None
    max: Optional[float] = None
    any_true_fails: Optional[list[dict]] = None
    sub_conditions: Optional[list[dict]] = None
    logic: Optional[str] = None  # AND | OR
    state_thresholds: Optional[dict[str, Any]] = None


class Rule(BaseModel):
    rule_id: str
    parameter: str
    description: str
    condition: RuleCondition
    is_mandatory: bool
    weight: int
    ambiguity_refs: list[str] = []
    ambiguity_note: Optional[str] = None


class RequiredDocument(BaseModel):
    document: str
    where_to_obtain: str
    processing_time_days: str
    priority: int


class Scheme(BaseModel):
    scheme_id: str
    name: str
    full_name: str
    target_description: str
    ministry: str
    data_source: str
    data_freshness: str
    rules: list[Rule]
    required_documents: list[RequiredDocument]
    prerequisites: list[str] = []
    benefit_summary: str
