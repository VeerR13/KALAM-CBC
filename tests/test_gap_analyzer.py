"""Tests for GapAnalyzer and DocumentChecklistGenerator."""
from src.models.scheme import RuleResult
from src.models.match_result import MatchResult, RuleEvaluation, GapItem
from src.engine.confidence import MatchStatus
from src.engine.gap_analyzer import GapAnalyzer
from src.engine.doc_checklist import DocumentChecklistGenerator


def _result(status: MatchStatus, evals: list[RuleEvaluation], prereqs: list[str] = [], docs: list[dict] = []) -> MatchResult:
    return MatchResult(
        scheme_id="test", scheme_name="Test", status=status,
        confidence=75.0, rule_evaluations=evals,
        prerequisite_scheme_ids=prereqs, required_documents=docs,
        benefit_summary="test",
    )


def _eval(result: RuleResult, explanation: str = "test", mandatory: bool = True) -> RuleEvaluation:
    return RuleEvaluation(rule_id="R01", result=result, explanation=explanation, is_mandatory=mandatory, weight=10)


# GapAnalyzer tests

def test_no_gaps_for_eligible():
    result = _result(MatchStatus.ELIGIBLE, [_eval(RuleResult.PASS)])
    assert GapAnalyzer.analyze(result) == []


def test_no_gaps_for_ineligible():
    result = _result(MatchStatus.INELIGIBLE, [_eval(RuleResult.FAIL)])
    assert GapAnalyzer.analyze(result) == []


def test_missing_input_flagged():
    result = _result(MatchStatus.AMBIGUOUS, [_eval(RuleResult.MISSING, "age not provided")])
    gaps = GapAnalyzer.analyze(result)
    assert any(g.gap_type == "MISSING_INPUT" for g in gaps)


def test_ambiguous_criterion_flagged():
    result = _result(MatchStatus.AMBIGUOUS, [_eval(RuleResult.AMBIGUOUS, "land tenure ambiguous")])
    gaps = GapAnalyzer.analyze(result)
    assert any(g.gap_type == "AMBIGUOUS_CRITERION" for g in gaps)


def test_missing_prerequisite_flagged():
    result = _result(MatchStatus.LIKELY_ELIGIBLE, [_eval(RuleResult.PASS)], prereqs=["pmjdy"])
    gaps = GapAnalyzer.analyze(result)
    assert any(g.gap_type == "MISSING_PREREQUISITE" for g in gaps)


def test_multiple_gap_types():
    evals = [
        _eval(RuleResult.MISSING, "income not provided"),
        _eval(RuleResult.AMBIGUOUS, "land tenure unclear"),
    ]
    result = _result(MatchStatus.AMBIGUOUS, evals, prereqs=["nfsa"])
    gaps = GapAnalyzer.analyze(result)
    types = {g.gap_type for g in gaps}
    assert "MISSING_INPUT" in types
    assert "AMBIGUOUS_CRITERION" in types
    assert "MISSING_PREREQUISITE" in types


# DocumentChecklistGenerator tests

def test_empty_for_ineligible():
    result = _result(MatchStatus.INELIGIBLE, [], docs=[{"document": "Aadhaar", "priority": 1}])
    assert DocumentChecklistGenerator.generate(result) == []


def test_docs_sorted_by_priority():
    docs = [
        {"document": "Land Records", "priority": 3},
        {"document": "Aadhaar", "priority": 1},
        {"document": "Bank Passbook", "priority": 2},
    ]
    result = _result(MatchStatus.ELIGIBLE, [], docs=docs)
    checklist = DocumentChecklistGenerator.generate(result)
    priorities = [d["priority"] for d in checklist]
    assert priorities == sorted(priorities)


def test_docs_returned_for_likely():
    docs = [{"document": "Aadhaar", "priority": 1}]
    result = _result(MatchStatus.LIKELY_ELIGIBLE, [], docs=docs)
    checklist = DocumentChecklistGenerator.generate(result)
    assert len(checklist) == 1
