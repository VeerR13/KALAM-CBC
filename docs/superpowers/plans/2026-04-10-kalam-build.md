# Kalam — Full Build Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, explainable welfare eligibility engine for 20 Indian government schemes with Hinglish CLI.

**Architecture:** JSON-driven rule engine (no hardcoded eligibility logic) → Pydantic profile model → confidence scorer → gap analyzer → prerequisite DAG → rich CLI with Claude API for Hinglish NLP.

**Tech Stack:** Python 3.11+, Pydantic v2, anthropic SDK, networkx, rich, typer, pytest

---

## PHASE 1: Scaffold & Scheme Knowledge Base

### Task 1.1: Python package init files

**Files:**
- Create: `src/__init__.py`
- Create: `src/models/__init__.py`
- Create: `src/engine/__init__.py`
- Create: `src/conversation/__init__.py`
- Create: `tests/__init__.py`

- [ ] Create all `__init__.py` files (empty)
- [ ] Commit: `git commit -m "chore: init python package structure"`

---

### Task 1.2: Data files — prerequisites.json + ambiguity_map.json + documents.json

**Files:**
- Create: `data/prerequisites.json`
- Create: `data/ambiguity_map.json`
- Create: `data/documents.json`

- [ ] Create `data/prerequisites.json`:
```json
{
  "edges": [
    {"from": "pmjdy", "to": "pm_kisan", "reason": "Aadhaar-seeded bank account required for DBT"},
    {"from": "pmjdy", "to": "ujjwala", "reason": "Bank account required for subsidy"},
    {"from": "pmjdy", "to": "pm_sym", "reason": "Savings bank account required"},
    {"from": "pmjdy", "to": "apy", "reason": "Savings bank account required"},
    {"from": "pmjdy", "to": "pmmvy", "reason": "Bank account for DBT"},
    {"from": "pmjdy", "to": "nsap_ignoaps", "reason": "Bank account for DBT"},
    {"from": "pmjdy", "to": "nsap_ignwps", "reason": "Bank account for DBT"},
    {"from": "pmjdy", "to": "nsap_igndps", "reason": "Bank account for DBT"},
    {"from": "nfsa", "to": "ujjwala", "reason": "AAY ration card is one qualifying category"},
    {"from": "nfsa", "to": "pmay_g", "reason": "SECC/BPL listing used for identification"},
    {"from": "pm_svanidhi", "to": "pm_svanidhi_loan2", "reason": "Must repay Loan 1 first"},
    {"from": "pm_svanidhi_loan2", "to": "pm_svanidhi_loan3", "reason": "Must repay Loan 2 first"}
  ]
}
```

- [ ] Create `data/ambiguity_map.json` with initial 10 entries (expand during human verification)
- [ ] Create `data/documents.json` with document checklist per scheme
- [ ] Commit

---

### Task 1.3: All 20 scheme JSON files

**Files:** `data/schemes/<scheme_id>.json` × 20

One per scheme. Each follows the schema:
```json
{
  "scheme_id": "...",
  "name": "...",
  "full_name": "...",
  "target_description": "...",
  "ministry": "...",
  "data_source": "...",
  "data_freshness": "PENDING_HUMAN_VERIFICATION",
  "rules": [...],
  "required_documents": [...],
  "prerequisites": [...],
  "benefit_summary": "..."
}
```

- [ ] Create all 20 JSONs (see scheme data below each task)
- [ ] Commit: `git commit -m "feat: add 20 scheme JSON rule files (pending verification)"`

---

### Task 1.4: src/loader.py

**Files:**
- Create: `src/loader.py`
- Test: `tests/test_loader.py`

- [ ] Write failing test:
```python
# tests/test_loader.py
from src.loader import load_scheme, load_all_schemes, load_prerequisites, load_ambiguity_map

def test_load_scheme_returns_dict():
    scheme = load_scheme("pm_kisan")
    assert scheme["scheme_id"] == "pm_kisan"
    assert "rules" in scheme
    assert "required_documents" in scheme

def test_load_all_schemes_returns_20():
    schemes = load_all_schemes()
    assert len(schemes) == 20

def test_load_prerequisites():
    prereqs = load_prerequisites()
    assert "edges" in prereqs
    assert len(prereqs["edges"]) > 0

def test_load_ambiguity_map():
    amb = load_ambiguity_map()
    assert isinstance(amb, list)
```

- [ ] Run: `pytest tests/test_loader.py -v` → expect FAIL
- [ ] Implement `src/loader.py`:
```python
"""Loads scheme JSONs, ambiguity map, prerequisites, and documents from data/."""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SCHEMES_DIR = DATA_DIR / "schemes"

def load_scheme(scheme_id: str) -> dict:
    """Load a single scheme JSON by scheme_id."""
    path = SCHEMES_DIR / f"{scheme_id}.json"
    with open(path) as f:
        return json.load(f)

def load_all_schemes() -> list[dict]:
    """Load all scheme JSONs from data/schemes/."""
    return [json.loads(p.read_text()) for p in sorted(SCHEMES_DIR.glob("*.json"))]

def load_prerequisites() -> dict:
    """Load prerequisite DAG edges."""
    with open(DATA_DIR / "prerequisites.json") as f:
        return json.load(f)

def load_ambiguity_map() -> list[dict]:
    """Load ambiguity annotations."""
    with open(DATA_DIR / "ambiguity_map.json") as f:
        return json.load(f)

def load_documents() -> dict:
    """Load document checklist data."""
    with open(DATA_DIR / "documents.json") as f:
        return json.load(f)
```

- [ ] Run: `pytest tests/test_loader.py -v` → expect PASS
- [ ] Commit: `git commit -m "feat: add scheme loader with tests"`

---

## PHASE 2: User Profile Model

### Task 2.1: UserProfile Pydantic model

**Files:**
- Create: `src/models/user_profile.py`
- Test: `tests/test_user_profile.py`

- [ ] Write failing tests:
```python
# tests/test_user_profile.py
import pytest
from pydantic import ValidationError
from src.models.user_profile import UserProfile, normalize_bigha_to_hectares

def test_valid_minimal_profile():
    p = UserProfile(
        age=34, state="Rajasthan", is_urban=False,
        caste_category="SC", gender="M",
        annual_income=80000, occupation="farmer",
        family_size=5, has_bank_account=True,
        has_aadhaar=True, is_aadhaar_linked=False,
    )
    assert p.age == 34
    assert p.state == "Rajasthan"

def test_invalid_age_rejected():
    with pytest.raises(ValidationError):
        UserProfile(age=-1, state="UP", is_urban=False,
                    caste_category="OBC", gender="F",
                    annual_income=50000, occupation="farmer",
                    family_size=3, has_bank_account=False,
                    has_aadhaar=False, is_aadhaar_linked=False)

def test_bigha_normalization_rajasthan():
    hectares = normalize_bigha_to_hectares(2.0, "Rajasthan")
    assert abs(hectares - 0.8) < 0.001

def test_bigha_normalization_up():
    hectares = normalize_bigha_to_hectares(2.0, "UP")
    assert abs(hectares - 0.66) < 0.01

def test_bigha_normalization_assam():
    hectares = normalize_bigha_to_hectares(2.0, "Assam")
    assert abs(hectares - 1.25) < 0.001

def test_income_is_approximate_flag():
    p = UserProfile(
        age=34, state="UP", is_urban=False, caste_category="OBC", gender="M",
        annual_income=85000, occupation="farmer", family_size=4,
        has_bank_account=True, has_aadhaar=True, is_aadhaar_linked=True,
        income_is_approximate=True, income_range=(80000, 90000)
    )
    assert p.income_is_approximate is True
    assert p.income_range == (80000, 90000)

def test_optional_fields_default_none():
    p = UserProfile(
        age=25, state="Bihar", is_urban=False, caste_category="ST", gender="F",
        annual_income=40000, occupation="agricultural_labourer", family_size=4,
        has_bank_account=False, has_aadhaar=True, is_aadhaar_linked=False,
    )
    assert p.land_ownership is None
    assert p.disability_percent is None
    assert p.marital_status is None
```

- [ ] Run: `pytest tests/test_user_profile.py -v` → expect FAIL
- [ ] Implement `src/models/user_profile.py`:
```python
"""Pydantic UserProfile model with unit normalization."""
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

BIGHA_TO_HECTARES: dict[str, float] = {
    "Rajasthan": 0.4,
    "UP": 0.33,
    "Uttar Pradesh": 0.33,
    "Bihar": 0.33,
    "Assam": 0.625,
    "Jharkhand": 0.33,
    "Madhya Pradesh": 0.33,
    "MP": 0.33,
    "West Bengal": 0.133,
    "Punjab": 0.553,
    "Haryana": 0.553,
    "Gujarat": 0.259,
}
DEFAULT_BIGHA_HECTARES = 0.4

def normalize_bigha_to_hectares(bigha: float, state: str) -> float:
    """Convert bigha to hectares using state-specific conversion factor."""
    factor = BIGHA_TO_HECTARES.get(state, DEFAULT_BIGHA_HECTARES)
    return round(bigha * factor, 4)

class UserProfile(BaseModel):
    """Complete user profile for welfare eligibility evaluation."""
    # Required fields
    age: int = Field(..., ge=0, le=150)
    state: str
    is_urban: bool
    caste_category: Literal["General", "OBC", "SC", "ST"]
    gender: Literal["M", "F", "Transgender"]
    annual_income: int = Field(..., ge=0)
    occupation: str
    family_size: int = Field(..., ge=1)
    has_bank_account: bool
    has_aadhaar: bool
    is_aadhaar_linked: bool

    # Conditional / Optional
    district: Optional[str] = None
    marital_status: Optional[Literal["unmarried", "married", "widowed", "divorced", "separated"]] = None
    land_ownership: Optional[Literal["owns", "leases", "sharecrop", "none"]] = None
    land_area_hectares: Optional[float] = None
    num_children: Optional[int] = None
    has_girl_child_under_10: Optional[bool] = None
    is_pregnant_or_lactating: Optional[bool] = None
    num_live_births: Optional[int] = None
    has_ration_card: Optional[Literal["AAY", "PHH", "none", "unknown"]] = None
    disability_percent: Optional[int] = Field(None, ge=0, le=100)
    is_govt_employee: Optional[bool] = None
    is_income_tax_payer: Optional[bool] = None
    has_existing_enterprise: Optional[bool] = None
    is_epf_member: Optional[bool] = None
    previous_scheme_loans: Optional[list[str]] = None

    # Metadata
    income_is_approximate: bool = False
    income_range: Optional[tuple[int, int]] = None
```

- [ ] Run: `pytest tests/test_user_profile.py -v` → expect PASS
- [ ] Commit: `git commit -m "feat: add UserProfile model with bigha normalization"`

---

## PHASE 3: Rule Engine

### Task 3.1: Scheme + Rule + RuleResult models

**Files:**
- Create: `src/models/scheme.py`
- Test: `tests/test_rule_engine.py` (partial)

- [ ] Implement `src/models/scheme.py`:
```python
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
    type: str  # field_check | exclusion | range_check | boolean_check | composite | state_dependent
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
```

### Task 3.2: Rule Engine evaluator

**Files:**
- Create: `src/engine/rule_engine.py`
- Test: `tests/test_rule_engine.py`

- [ ] Write failing tests:
```python
# tests/test_rule_engine.py
from src.models.scheme import RuleResult, Rule, RuleCondition
from src.models.user_profile import UserProfile
from src.engine.rule_engine import evaluate_rule, evaluate_scheme
from src.loader import load_scheme
from src.models.scheme import Scheme

def _make_profile(**kwargs) -> UserProfile:
    defaults = dict(
        age=34, state="Rajasthan", is_urban=False, caste_category="SC",
        gender="M", annual_income=80000, occupation="farmer", family_size=5,
        has_bank_account=True, has_aadhaar=True, is_aadhaar_linked=True,
        land_ownership="owns", land_area_hectares=0.8,
    )
    defaults.update(kwargs)
    return UserProfile(**defaults)

def test_field_check_pass():
    rule = Rule(rule_id="T01", parameter="land_ownership", description="test",
                condition=RuleCondition(type="field_check", field="land_ownership",
                                        values=["owns"], ambiguous_values=["leases", "sharecrop"]),
                is_mandatory=True, weight=10)
    result, explanation = evaluate_rule(rule, _make_profile(land_ownership="owns"))
    assert result == RuleResult.PASS

def test_field_check_ambiguous():
    rule = Rule(rule_id="T02", parameter="land_ownership", description="test",
                condition=RuleCondition(type="field_check", field="land_ownership",
                                        values=["owns"], ambiguous_values=["leases", "sharecrop"]),
                is_mandatory=True, weight=10)
    result, explanation = evaluate_rule(rule, _make_profile(land_ownership="leases"))
    assert result == RuleResult.AMBIGUOUS

def test_field_check_fail():
    rule = Rule(rule_id="T03", parameter="land_ownership", description="test",
                condition=RuleCondition(type="field_check", field="land_ownership",
                                        values=["owns"], ambiguous_values=[]),
                is_mandatory=True, weight=10)
    result, explanation = evaluate_rule(rule, _make_profile(land_ownership="none"))
    assert result == RuleResult.FAIL

def test_missing_field_returns_missing():
    rule = Rule(rule_id="T04", parameter="disability_percent", description="test",
                condition=RuleCondition(type="range_check", field="disability_percent",
                                        min=40.0, max=100.0),
                is_mandatory=True, weight=10)
    result, explanation = evaluate_rule(rule, _make_profile())  # disability_percent=None
    assert result == RuleResult.MISSING

def test_range_check_pass():
    rule = Rule(rule_id="T05", parameter="age", description="test",
                condition=RuleCondition(type="range_check", field="age", min=18.0, max=40.0),
                is_mandatory=True, weight=10)
    result, _ = evaluate_rule(rule, _make_profile(age=30))
    assert result == RuleResult.PASS

def test_range_check_fail():
    rule = Rule(rule_id="T06", parameter="age", description="test",
                condition=RuleCondition(type="range_check", field="age", min=18.0, max=40.0),
                is_mandatory=True, weight=10)
    result, _ = evaluate_rule(rule, _make_profile(age=50))
    assert result == RuleResult.FAIL

def test_exclusion_fails_when_true():
    rule = Rule(rule_id="T07", parameter="exclusion", description="test",
                condition=RuleCondition(type="exclusion",
                                        any_true_fails=[{"field": "is_income_tax_payer", "equals": True}]),
                is_mandatory=True, weight=10)
    result, _ = evaluate_rule(rule, _make_profile(is_income_tax_payer=True))
    assert result == RuleResult.FAIL

def test_boolean_check_pass():
    rule = Rule(rule_id="T08", parameter="has_bank_account", description="test",
                condition=RuleCondition(type="boolean_check", field="has_bank_account", equals=True),
                is_mandatory=True, weight=10)
    result, _ = evaluate_rule(rule, _make_profile(has_bank_account=True))
    assert result == RuleResult.PASS

def test_evaluate_scheme_pm_kisan_basic():
    scheme_data = load_scheme("pm_kisan")
    scheme = Scheme(**scheme_data)
    profile = _make_profile(land_ownership="owns", is_income_tax_payer=False, is_govt_employee=False)
    results = evaluate_scheme(scheme, profile)
    assert len(results) == len(scheme.rules)
    # All results are (rule_id, RuleResult, str) tuples
    for rule_id, result, explanation in results:
        assert isinstance(result, RuleResult)
        assert isinstance(explanation, str)
```

- [ ] Run `pytest tests/test_rule_engine.py -v` → expect FAIL
- [ ] Implement `src/engine/rule_engine.py`:
```python
"""Deterministic rule evaluator. Takes a Rule + UserProfile → RuleResult + explanation."""
from src.models.scheme import Rule, RuleResult, Scheme
from src.models.user_profile import UserProfile

def evaluate_rule(rule: Rule, profile: UserProfile) -> tuple[RuleResult, str]:
    """Evaluate a single rule against a profile. Returns (RuleResult, explanation)."""
    cond = rule.condition

    if cond.type == "field_check":
        value = getattr(profile, cond.field, None)
        if value is None:
            return RuleResult.MISSING, f"{cond.field} not provided"
        if cond.values and value in cond.values:
            return RuleResult.PASS, f"{cond.field}={value} matches required {cond.values}"
        if cond.ambiguous_values and value in cond.ambiguous_values:
            return RuleResult.AMBIGUOUS, f"{cond.field}={value} is in ambiguous set — eligibility unclear"
        return RuleResult.FAIL, f"{cond.field}={value} not in required {cond.values}"

    elif cond.type == "boolean_check":
        value = getattr(profile, cond.field, None)
        if value is None:
            return RuleResult.MISSING, f"{cond.field} not provided"
        if value == cond.equals:
            return RuleResult.PASS, f"{cond.field} is {value}"
        return RuleResult.FAIL, f"{cond.field} is {value}, required {cond.equals}"

    elif cond.type == "range_check":
        value = getattr(profile, cond.field, None)
        if value is None:
            return RuleResult.MISSING, f"{cond.field} not provided"
        in_range = True
        if cond.min is not None and value < cond.min:
            in_range = False
        if cond.max is not None and value > cond.max:
            in_range = False
        if in_range:
            return RuleResult.PASS, f"{cond.field}={value} within [{cond.min}, {cond.max}]"
        return RuleResult.FAIL, f"{cond.field}={value} outside [{cond.min}, {cond.max}]"

    elif cond.type == "exclusion":
        if not cond.any_true_fails:
            return RuleResult.PASS, "No exclusion criteria"
        for criterion in cond.any_true_fails:
            field = criterion.get("field")
            expected = criterion.get("equals")
            value = getattr(profile, field, None)
            if value is None:
                continue  # Missing field doesn't trigger exclusion
            if value == expected:
                return RuleResult.FAIL, f"Excluded: {field}={value}"
        return RuleResult.PASS, "No exclusion criteria matched"

    elif cond.type == "composite":
        if not cond.sub_conditions:
            return RuleResult.MISSING, "No sub-conditions defined"
        sub_results = []
        for sub in cond.sub_conditions:
            from src.models.scheme import Rule, RuleCondition
            sub_rule = Rule(rule_id=f"{rule.rule_id}_sub", parameter="sub",
                           description="sub", condition=RuleCondition(**sub),
                           is_mandatory=False, weight=0)
            sub_result, sub_exp = evaluate_rule(sub_rule, profile)
            sub_results.append((sub_result, sub_exp))
        logic = cond.logic or "AND"
        if logic == "AND":
            if all(r == RuleResult.PASS for r, _ in sub_results):
                return RuleResult.PASS, "All sub-conditions met"
            if any(r == RuleResult.FAIL for r, _ in sub_results):
                return RuleResult.FAIL, "One or more sub-conditions failed"
            if any(r == RuleResult.AMBIGUOUS for r, _ in sub_results):
                return RuleResult.AMBIGUOUS, "One or more sub-conditions ambiguous"
            return RuleResult.MISSING, "Insufficient data for composite rule"
        else:  # OR
            if any(r == RuleResult.PASS for r, _ in sub_results):
                return RuleResult.PASS, "At least one sub-condition met"
            if any(r == RuleResult.AMBIGUOUS for r, _ in sub_results):
                return RuleResult.AMBIGUOUS, "Sub-conditions ambiguous"
            return RuleResult.FAIL, "No sub-conditions met"

    elif cond.type == "state_dependent":
        if not cond.state_thresholds:
            return RuleResult.MISSING, "No state thresholds defined"
        threshold = cond.state_thresholds.get(profile.state, cond.state_thresholds.get("default"))
        if threshold is None:
            return RuleResult.AMBIGUOUS, f"No threshold defined for state={profile.state}"
        value = getattr(profile, cond.field, None)
        if value is None:
            return RuleResult.MISSING, f"{cond.field} not provided"
        if value <= threshold:
            return RuleResult.PASS, f"{cond.field}={value} <= state threshold {threshold}"
        return RuleResult.FAIL, f"{cond.field}={value} exceeds state threshold {threshold}"

    return RuleResult.MISSING, f"Unknown condition type: {cond.type}"


def evaluate_scheme(scheme: Scheme, profile: UserProfile) -> list[tuple[str, RuleResult, str]]:
    """Evaluate all rules in a scheme. Returns list of (rule_id, RuleResult, explanation)."""
    return [(rule.rule_id, *evaluate_rule(rule, profile)) for rule in scheme.rules]
```

- [ ] Run `pytest tests/test_rule_engine.py -v` → expect PASS
- [ ] Commit: `git commit -m "feat: add rule engine with 6 condition types + tests"`

---

## PHASE 4: Confidence Scorer

### Task 4.1: MatchResult model + ConfidenceScorer

**Files:**
- Create: `src/models/match_result.py`
- Create: `src/engine/confidence.py`
- Test: `tests/test_confidence.py`

- [ ] Write failing tests:
```python
# tests/test_confidence.py
from src.models.scheme import RuleResult, Rule, RuleCondition, Scheme, RequiredDocument
from src.engine.confidence import ConfidenceScorer, MatchStatus

def _make_scheme_with_rules(rules_spec: list[dict]) -> Scheme:
    rules = []
    for i, spec in enumerate(rules_spec):
        rules.append(Rule(
            rule_id=f"R{i:02d}", parameter=f"param_{i}", description=f"rule {i}",
            condition=RuleCondition(type="boolean_check", field="has_bank_account", equals=True),
            is_mandatory=spec["mandatory"], weight=spec["weight"]
        ))
    return Scheme(scheme_id="test", name="Test", full_name="Test Scheme",
                  target_description="test", ministry="test", data_source="test",
                  data_freshness="test", rules=rules, required_documents=[],
                  benefit_summary="test")

def test_all_pass_eligible():
    rule_results = [("R00", RuleResult.PASS, "ok"), ("R01", RuleResult.PASS, "ok")]
    scheme = _make_scheme_with_rules([{"mandatory": True, "weight": 50}, {"mandatory": True, "weight": 50}])
    score, status = ConfidenceScorer.score(scheme, rule_results)
    assert score == 100.0
    assert status == MatchStatus.ELIGIBLE

def test_mandatory_fail_ineligible():
    rule_results = [("R00", RuleResult.FAIL, "fail"), ("R01", RuleResult.PASS, "ok")]
    scheme = _make_scheme_with_rules([{"mandatory": True, "weight": 50}, {"mandatory": False, "weight": 50}])
    score, status = ConfidenceScorer.score(scheme, rule_results)
    assert status == MatchStatus.INELIGIBLE

def test_ambiguous_scores_half_weight():
    rule_results = [("R00", RuleResult.AMBIGUOUS, "amb"), ("R01", RuleResult.PASS, "ok")]
    scheme = _make_scheme_with_rules([{"mandatory": False, "weight": 50}, {"mandatory": True, "weight": 50}])
    score, status = ConfidenceScorer.score(scheme, rule_results)
    # (0.5*50 + 50) / 100 * 100 = 75.0
    assert abs(score - 75.0) < 0.01
    assert status == MatchStatus.LIKELY_ELIGIBLE

def test_all_missing_returns_insufficient():
    rule_results = [("R00", RuleResult.MISSING, "missing")]
    scheme = _make_scheme_with_rules([{"mandatory": True, "weight": 100}])
    score, status = ConfidenceScorer.score(scheme, rule_results)
    assert status == MatchStatus.INSUFFICIENT_DATA

def test_mandatory_ambiguous_is_ambiguous_status():
    rule_results = [("R00", RuleResult.AMBIGUOUS, "amb"), ("R01", RuleResult.PASS, "ok")]
    scheme = _make_scheme_with_rules([{"mandatory": True, "weight": 50}, {"mandatory": True, "weight": 50}])
    score, status = ConfidenceScorer.score(scheme, rule_results)
    assert status == MatchStatus.AMBIGUOUS
```

- [ ] Run `pytest tests/test_confidence.py -v` → expect FAIL
- [ ] Implement `src/engine/confidence.py`:
```python
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
    """Computes confidence score and match status for a scheme evaluation."""

    @staticmethod
    def score(scheme: Scheme, rule_results: list[tuple[str, RuleResult, str]]) -> tuple[float, MatchStatus]:
        """
        Formula: (sum_passed + 0.5 * sum_ambiguous) / sum_evaluated * 100
        MISSING rules are excluded from sum_evaluated.
        """
        rule_map = {r.rule_id: r for r in scheme.rules}
        results_map = {rid: (result, exp) for rid, result, exp in rule_results}

        sum_passed = 0.0
        sum_ambiguous = 0.0
        sum_evaluated = 0.0
        has_mandatory_fail = False
        has_mandatory_ambiguous = False

        for rule_id, (result, _) in results_map.items():
            rule = rule_map.get(rule_id)
            if rule is None:
                continue
            if result == RuleResult.MISSING:
                continue
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

        if sum_evaluated == 0:
            return 0.0, MatchStatus.INSUFFICIENT_DATA

        if has_mandatory_fail:
            return 0.0, MatchStatus.INELIGIBLE

        confidence = (sum_passed + 0.5 * sum_ambiguous) / sum_evaluated * 100

        if confidence >= 90 and not has_mandatory_ambiguous:
            return confidence, MatchStatus.ELIGIBLE
        elif confidence >= 70 and not has_mandatory_fail:
            return confidence, MatchStatus.LIKELY_ELIGIBLE
        elif has_mandatory_ambiguous or (40 <= confidence < 70):
            return confidence, MatchStatus.AMBIGUOUS
        else:
            return confidence, MatchStatus.INELIGIBLE
```

- [ ] Implement `src/models/match_result.py`:
```python
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
    gap_type: str  # MISSING_DOCUMENT | MISSING_PREREQUISITE | AMBIGUOUS_CRITERION | MISSING_INPUT
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
```

- [ ] Run `pytest tests/test_confidence.py -v` → expect PASS
- [ ] Commit: `git commit -m "feat: add confidence scorer and match result models"`

---

## PHASE 5: Gap Analyzer & Document Checklist

### Task 5.1: GapAnalyzer

**Files:**
- Create: `src/engine/gap_analyzer.py`
- Create: `src/engine/doc_checklist.py`
- Test: `tests/test_gap_analyzer.py`

- [ ] Write failing tests:
```python
# tests/test_gap_analyzer.py
from src.models.scheme import RuleResult, Scheme, Rule, RuleCondition, RequiredDocument
from src.models.match_result import MatchResult, RuleEvaluation
from src.engine.confidence import MatchStatus
from src.engine.gap_analyzer import GapAnalyzer
from src.engine.doc_checklist import DocumentChecklistGenerator

def _make_match_result(status, evals, scheme_id="test") -> MatchResult:
    return MatchResult(
        scheme_id=scheme_id, scheme_name="Test",
        status=status, confidence=75.0,
        rule_evaluations=evals,
        benefit_summary="test benefit",
    )

def test_missing_input_flagged():
    evals = [RuleEvaluation(rule_id="R01", result=RuleResult.MISSING,
                             explanation="age not provided", is_mandatory=True, weight=10)]
    result = _make_match_result(MatchStatus.AMBIGUOUS, evals)
    gaps = GapAnalyzer.analyze(result)
    types = [g.gap_type for g in gaps]
    assert "MISSING_INPUT" in types

def test_ambiguous_criterion_flagged():
    evals = [RuleEvaluation(rule_id="R01", result=RuleResult.AMBIGUOUS,
                             explanation="land tenure ambiguous", is_mandatory=True, weight=10)]
    result = _make_match_result(MatchStatus.AMBIGUOUS, evals)
    gaps = GapAnalyzer.analyze(result)
    types = [g.gap_type for g in gaps]
    assert "AMBIGUOUS_CRITERION" in types

def test_no_gaps_for_eligible():
    evals = [RuleEvaluation(rule_id="R01", result=RuleResult.PASS,
                             explanation="ok", is_mandatory=True, weight=10)]
    result = _make_match_result(MatchStatus.ELIGIBLE, evals)
    gaps = GapAnalyzer.analyze(result)
    assert gaps == []
```

- [ ] Run `pytest tests/test_gap_analyzer.py -v` → expect FAIL
- [ ] Implement `src/engine/gap_analyzer.py`:
```python
"""Generates gap analysis from a MatchResult."""
from src.models.match_result import MatchResult, GapItem
from src.models.scheme import RuleResult
from src.engine.confidence import MatchStatus

class GapAnalyzer:
    @staticmethod
    def analyze(result: MatchResult) -> list[GapItem]:
        """Return list of gaps for LIKELY_ELIGIBLE and AMBIGUOUS results."""
        if result.status == MatchStatus.ELIGIBLE:
            return []
        if result.status == MatchStatus.INELIGIBLE:
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

        if result.prerequisite_scheme_ids:
            for prereq_id in result.prerequisite_scheme_ids:
                gaps.append(GapItem(
                    gap_type="MISSING_PREREQUISITE",
                    description=f"Scheme '{prereq_id}' must be enrolled first.",
                    action=f"Apply for {prereq_id} before this scheme.",
                ))

        return gaps
```

- [ ] Implement `src/engine/doc_checklist.py`:
```python
"""Generates prioritized document checklist for eligible/likely schemes."""
from src.models.match_result import MatchResult
from src.engine.confidence import MatchStatus

class DocumentChecklistGenerator:
    @staticmethod
    def generate(result: MatchResult) -> list[dict]:
        """Return documents sorted by priority (fastest processing first)."""
        if result.status == MatchStatus.INELIGIBLE:
            return []
        docs = sorted(result.required_documents, key=lambda d: d.get("priority", 99))
        return docs
```

- [ ] Run `pytest tests/test_gap_analyzer.py -v` → expect PASS
- [ ] Commit: `git commit -m "feat: add gap analyzer and document checklist generator"`

---

## PHASE 6: Prerequisite DAG & Sequencer

### Task 6.1: PrerequisiteDAG

**Files:**
- Create: `src/engine/sequencer.py`
- Test: `tests/test_sequencer.py`

- [ ] Write failing tests:
```python
# tests/test_sequencer.py
from src.engine.sequencer import PrerequisiteDAG
from src.engine.confidence import MatchStatus

def test_topological_order_pmjdy_before_pm_kisan():
    dag = PrerequisiteDAG()
    dag.add_edge("pmjdy", "pm_kisan", "Bank account required")
    order = dag.topological_order(["pmjdy", "pm_kisan"])
    assert order.index("pmjdy") < order.index("pm_kisan")

def test_no_cycles():
    dag = PrerequisiteDAG()
    dag.add_edge("pmjdy", "pm_kisan", "reason")
    assert dag.has_cycle() is False

def test_skip_already_enrolled():
    dag = PrerequisiteDAG()
    dag.add_edge("pmjdy", "pm_kisan", "reason")
    order = dag.topological_order(["pmjdy", "pm_kisan"], already_enrolled={"pmjdy"})
    assert "pmjdy" not in order
    assert "pm_kisan" in order

def test_load_from_data():
    dag = PrerequisiteDAG.from_data_file()
    assert dag.graph.number_of_edges() > 0
```

- [ ] Run `pytest tests/test_sequencer.py -v` → expect FAIL
- [ ] Implement `src/engine/sequencer.py`:
```python
"""Prerequisite DAG using networkx for scheme application ordering."""
import networkx as nx
from src.loader import load_prerequisites

class PrerequisiteDAG:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_edge(self, from_scheme: str, to_scheme: str, reason: str) -> None:
        self.graph.add_edge(from_scheme, to_scheme, reason=reason)

    def has_cycle(self) -> bool:
        return not nx.is_directed_acyclic_graph(self.graph)

    def topological_order(self, scheme_ids: list[str], already_enrolled: set[str] | None = None) -> list[str]:
        """Return scheme_ids in dependency-respecting application order."""
        already_enrolled = already_enrolled or set()
        subgraph = self.graph.subgraph(scheme_ids)
        try:
            order = list(nx.topological_sort(subgraph))
        except nx.NetworkXUnfeasible:
            order = scheme_ids  # fallback if cycle detected
        return [s for s in order if s not in already_enrolled]

    @classmethod
    def from_data_file(cls) -> "PrerequisiteDAG":
        """Load DAG from data/prerequisites.json."""
        dag = cls()
        data = load_prerequisites()
        for edge in data.get("edges", []):
            dag.add_edge(edge["from"], edge["to"], edge.get("reason", ""))
        return dag
```

- [ ] Run `pytest tests/test_sequencer.py -v` → expect PASS
- [ ] Commit: `git commit -m "feat: add prerequisite DAG with topological sort"`

---

## PHASE 7: Edge Case Test Harness (10 profiles)

### Task 7.1: 10 fixture profiles + expected results

**Files:**
- Create: `tests/fixtures/profiles/edge_01_remarried_widow.json` through `edge_10_disabled_no_aadhaar.json`
- Create: `tests/fixtures/expected_results/edge_01_expected.json` through `edge_10_expected.json`
- Create: `tests/test_edge_cases.py`

- [ ] Create 10 profile fixtures (see spec for field values)
- [ ] Create 10 expected result fixtures
- [ ] Write `tests/test_edge_cases.py` to load each fixture and assert status + ambiguity flags
- [ ] Commit: `git commit -m "test: add 10 adversarial edge case fixtures"`

---

## PHASE 8: Conversational Interface

### Task 8.1: System prompt + Hinglish parser

**Files:**
- Create: `src/conversation/system_prompt.py`
- Create: `src/conversation/hinglish_parser.py`
- Create: `src/conversation/follow_up.py`
- Create: `src/conversation/contradiction.py`
- Create: `src/formatter.py`
- Create: `cli.py`
- Test: `tests/test_hinglish.py`, `tests/test_contradiction.py`

- [ ] Implement system prompt, parser, follow-up, contradiction detector
- [ ] Implement `src/formatter.py` using `rich` tables and panels
- [ ] Build `cli.py` main loop with typer
- [ ] Write tests for contradiction detection
- [ ] Commit: `git commit -m "feat: add Hinglish CLI with Claude API NLP"`

---

## PHASE 9: Web UI (Stretch)

### Task 9.1: FastAPI app

**Files:**
- Create: `web/app.py`

- [ ] Implement single chat endpoint
- [ ] Basic HTML/CSS chat interface
- [ ] Commit: `git commit -m "feat: add FastAPI web UI (stretch goal)"`

---

## PHASE 10: Diagrams & Docs

### Task 10.1: Mermaid diagrams + README + CLAUDE.md

**Files:**
- Create: `diagrams/architecture.mermaid`
- Create: `diagrams/prerequisite_dag.mermaid`
- Create: `README.md`
- Create: `CLAUDE.md`

- [ ] Write Mermaid architecture diagram from spec Section 2
- [ ] Write prerequisite DAG Mermaid from data/prerequisites.json edges
- [ ] Write README with setup + usage instructions
- [ ] Write CLAUDE.md pointing to this spec
- [ ] Commit: `git commit -m "docs: add architecture diagrams and README"`
