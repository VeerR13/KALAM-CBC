"""Tests for src/loader.py."""
from src.loader import load_scheme, load_all_schemes, load_prerequisites, load_ambiguity_map


def test_load_scheme_pm_kisan():
    scheme = load_scheme("pm_kisan")
    assert scheme["scheme_id"] == "pm_kisan"
    assert "rules" in scheme
    assert "required_documents" in scheme
    assert scheme["data_freshness"].startswith("VERIFIED_AGAINST_PDF") or scheme["data_freshness"] == "PENDING_HUMAN_VERIFICATION"


def test_load_all_schemes_returns_20():
    schemes = load_all_schemes()
    assert len(schemes) == 20


def test_all_schemes_have_required_fields():
    schemes = load_all_schemes()
    for s in schemes:
        assert "scheme_id" in s
        assert "rules" in s
        assert "required_documents" in s
        assert "prerequisites" in s
        assert len(s["rules"]) > 0


def test_load_prerequisites():
    prereqs = load_prerequisites()
    assert "edges" in prereqs
    assert len(prereqs["edges"]) > 0
    edge = prereqs["edges"][0]
    assert "from" in edge
    assert "to" in edge


def test_load_ambiguity_map():
    amb = load_ambiguity_map()
    assert isinstance(amb, list)
    assert len(amb) > 0
    assert "id" in amb[0]
    assert "schemes_affected" in amb[0]
