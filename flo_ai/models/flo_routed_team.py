from flo_ai.models.flo_executable import ExecutableFlo
from langgraph.graph.graph import CompiledGraph


class FloRoutedTeam(ExecutableFlo):
    def __init__(self, name: str, graph: CompiledGraph) -> None:
        super().__init__(name, graph)

    # Overridden for xray use, doesnt work in base class
    def draw(self, xray=True):
        return self.runnable.get_graph(xray=xray).draw_mermaid_png()
