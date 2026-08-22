"""Graph topologies — the paper's structural dimension."""

from schemaeval.topologies.sequential import run_sequential_graph

# Later:
# from schemaeval.topologies.fanout import run_fanout_graph
# from schemaeval.topologies.router import run_router_graph
# from schemaeval.topologies.evaluator import run_evaluator_graph

__all__ = ["run_sequential_graph"]
