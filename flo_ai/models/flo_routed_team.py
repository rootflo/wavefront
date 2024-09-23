from flo_ai.models.flo_executable import ExecutableFlo
from langgraph.graph.graph import CompiledGraph
from flo_ai.yaml.config import TeamConfig

class FloRoutedTeam(ExecutableFlo):

    def __init__(self, name: str, graph: CompiledGraph, config: TeamConfig) -> None:
        super().__init__(name, graph)
        self.config = config

    # Overridden for xray use, doesnt work in base class
    def draw(self, xray=True):
        return self.runnable.get_graph(xray=xray).draw_mermaid_png()