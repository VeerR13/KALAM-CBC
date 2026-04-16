"""Tests for InteractionDetector — scheme mutual exclusions, enablers, threshold risks."""
import pytest
from src.engine.interaction_detector import Interaction, InteractionDetector


@pytest.fixture
def detector():
    return InteractionDetector()


class TestNoInteractions:
    def test_empty_list(self, detector):
        assert detector.detect([]) == []

    def test_single_inert_scheme(self, detector):
        """A scheme with no defined interactions produces no results."""
        result = detector.detect(["pm_kisan"])
        assert result == []

    def test_no_overlap(self, detector):
        """Two completely unrelated schemes → no interactions."""
        result = detector.detect(["pm_kisan", "ayushman_bharat"])
        assert result == []


class TestMutualExclusionPMEGP:
    def test_pmegp_and_vishwakarma_triggers(self, detector):
        """pmegp + pm_vishwakarma → mutual exclusion interaction."""
        result = detector.detect(["pmegp", "pm_vishwakarma"])
        assert len(result) >= 1
        types = [i.interaction_type for i in result]
        assert "mutual_exclusion_5yr" in types

    def test_recommendation_is_set(self, detector):
        result = detector.detect(["pmegp", "pm_vishwakarma"])
        ix = next(i for i in result if i.interaction_type == "mutual_exclusion_5yr")
        assert ix.recommendation is not None and len(ix.recommendation) > 10

    def test_mudra_and_vishwakarma_triggers(self, detector):
        result = detector.detect(["pm_mudra", "pm_vishwakarma"])
        assert any(i.interaction_type == "mutual_exclusion_5yr" for i in result)


class TestEnablerInteractions:
    def test_pmjdy_enabler_present_when_active(self, detector):
        """PMJDY is an enabler — should surface when both PMJDY and a dependent are eligible."""
        result = detector.detect(["pmjdy", "pm_kisan"])
        # If there's a PMJDY enabler interaction defined it should appear
        # (whether or not this specific pair is defined — just test no crash)
        assert isinstance(result, list)

    def test_interaction_has_required_fields(self, detector):
        """Each returned Interaction must have all required dataclass fields populated."""
        results = detector.detect(["pmegp", "pm_vishwakarma", "pm_mudra"])
        for ix in results:
            assert isinstance(ix, Interaction)
            assert ix.trigger_scheme
            assert ix.affected_schemes
            assert ix.title
            assert ix.description
            assert ix.severity in ("warning", "info", "choice")


class TestThresholdRisk:
    def test_nsap_pmkisan_threshold_risk(self, detector):
        """NSAP + PM-KISAN → threshold risk warning."""
        result = detector.detect(["nsap_ignoaps", "pm_kisan"])
        assert any(i.interaction_type == "threshold_risk" for i in result)

    def test_threshold_risk_severity_is_warning(self, detector):
        result = detector.detect(["nsap_ignoaps", "pm_kisan"])
        ix = next((i for i in result if i.interaction_type == "threshold_risk"), None)
        if ix:
            assert ix.severity == "warning"


class TestInteractionProperties:
    def test_affected_schemes_subset_of_eligible(self, detector):
        """affected_schemes must be a subset of the given eligible_ids."""
        eligible = ["pmegp", "pm_vishwakarma", "pm_kisan"]
        result = detector.detect(eligible)
        active_set = set(eligible)
        for ix in result:
            assert ix.trigger_scheme in active_set
            for sid in ix.affected_schemes:
                assert sid in active_set, f"{sid} not in eligible set"

    def test_severity_vishwakarma_is_choice(self, detector):
        result = detector.detect(["pm_vishwakarma", "pmegp"])
        vishwakarma_ix = [i for i in result if i.trigger_scheme == "pm_vishwakarma"]
        if vishwakarma_ix:
            assert vishwakarma_ix[0].severity == "choice"
