"""Prerequisite DAG using networkx for scheme application ordering."""
import networkx as nx
from src.loader import load_prerequisites


class PrerequisiteDAG:
    """Directed acyclic graph of scheme prerequisites."""

    def __init__(self) -> None:
        self.graph: nx.DiGraph = nx.DiGraph()

    def add_edge(self, from_scheme: str, to_scheme: str, reason: str) -> None:
        """Add a prerequisite edge: from_scheme must be done before to_scheme."""
        self.graph.add_edge(from_scheme, to_scheme, reason=reason)

    def has_cycle(self) -> bool:
        """Return True if the graph contains a cycle (should never happen)."""
        return not nx.is_directed_acyclic_graph(self.graph)

    def topological_order(
        self,
        scheme_ids: list[str],
        already_enrolled: set[str] | None = None,
    ) -> list[str]:
        """
        Return scheme_ids in dependency-respecting application order.
        Schemes in already_enrolled are excluded from the result.
        """
        already_enrolled = already_enrolled or set()
        # Ensure all scheme_ids appear as nodes even if they have no edges
        temp_graph = self.graph.copy()
        for s in scheme_ids:
            temp_graph.add_node(s)
        subgraph = temp_graph.subgraph(scheme_ids)
        try:
            order = list(nx.topological_sort(subgraph))
        except nx.NetworkXUnfeasible:
            order = list(scheme_ids)  # fallback: no ordering guarantee
        return [s for s in order if s not in already_enrolled]

    def prerequisites_for(self, scheme_id: str) -> list[str]:
        """Return direct prerequisites for a scheme."""
        return list(self.graph.predecessors(scheme_id))

    @classmethod
    def from_data_file(cls) -> "PrerequisiteDAG":
        """Load DAG from data/prerequisites.json."""
        dag = cls()
        data = load_prerequisites()
        for edge in data.get("edges", []):
            dag.add_edge(edge["from"], edge["to"], edge.get("reason", ""))
        return dag
