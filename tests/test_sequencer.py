"""Tests for PrerequisiteDAG."""
from src.engine.sequencer import PrerequisiteDAG


def test_topological_order_pmjdy_before_pm_kisan():
    dag = PrerequisiteDAG()
    dag.add_edge("pmjdy", "pm_kisan", "Bank account required")
    order = dag.topological_order(["pmjdy", "pm_kisan"])
    assert order.index("pmjdy") < order.index("pm_kisan")


def test_no_cycles_in_empty_dag():
    dag = PrerequisiteDAG()
    assert dag.has_cycle() is False


def test_no_cycles_in_linear_chain():
    dag = PrerequisiteDAG()
    dag.add_edge("pmjdy", "pm_kisan", "reason")
    dag.add_edge("pm_kisan", "pmegp", "reason")
    assert dag.has_cycle() is False


def test_skip_already_enrolled():
    dag = PrerequisiteDAG()
    dag.add_edge("pmjdy", "pm_kisan", "reason")
    order = dag.topological_order(["pmjdy", "pm_kisan"], already_enrolled={"pmjdy"})
    assert "pmjdy" not in order
    assert "pm_kisan" in order


def test_single_scheme_no_prerequisites():
    dag = PrerequisiteDAG()
    order = dag.topological_order(["mgnrega"])
    assert order == ["mgnrega"]


def test_prerequisites_for():
    dag = PrerequisiteDAG()
    dag.add_edge("pmjdy", "pm_kisan", "reason")
    dag.add_edge("nfsa", "ujjwala", "reason")
    dag.add_edge("pmjdy", "ujjwala", "reason")
    prereqs = dag.prerequisites_for("ujjwala")
    assert set(prereqs) == {"nfsa", "pmjdy"}


def test_load_from_data_file():
    dag = PrerequisiteDAG.from_data_file()
    assert dag.graph.number_of_edges() > 0
    assert not dag.has_cycle()


def test_load_from_data_pmjdy_before_pm_kisan():
    dag = PrerequisiteDAG.from_data_file()
    order = dag.topological_order(["pmjdy", "pm_kisan"])
    assert order.index("pmjdy") < order.index("pm_kisan")
