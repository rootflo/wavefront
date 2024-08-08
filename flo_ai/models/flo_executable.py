from flo_ai.models.flo_member import FloMember
from langgraph.graph.graph import CompiledGraph
from langchain_core.messages import HumanMessage

class ExecutableFlo(FloMember):
    def __init__(self, name: str, graph: CompiledGraph, type: str = "team") -> None:
        super().__init__(name, type)
        self.graph = graph

    def stream(self, work, config = None):
        return self.graph.stream({
             "messages": [
                HumanMessage(content=work)
            ]
        }, config)
    
    def invoke(self, work, config = None):
        return self.graph.invoke({
             "messages": [
                HumanMessage(content=work)
            ]
        }, config)