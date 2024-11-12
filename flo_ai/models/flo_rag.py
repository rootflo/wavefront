from typing import Optional
from langchain_core.language_models import BaseLanguageModel
from langchain.tools import Tool
from langgraph.graph import END, StateGraph
from langgraph.graph.graph import CompiledGraph
from langgraph.prebuilt import ToolNode
from flo_ai.state.flo_state import TeamFloAgentState
from langgraph.prebuilt import tools_condition
from flo_ai.models.flo_executable import ExecutableFlo
from langchain import hub
from langchain.prompts import ChatPromptTemplate


class FloRag(ExecutableFlo):
    def __init__(self, name: str, graph: CompiledGraph) -> None:
        super().__init__(name, 'team')
        self.graph = graph

    def draw(self, xray=True):
        return self.graph.get_graph(xray=xray).draw_mermaid_png()


class FloRagBuilder:
    def __init__(
        self,
        name: str,
        tools: list[Tool],
        llm: BaseLanguageModel,
        prompt: Optional[ChatPromptTemplate] = None,
    ) -> None:
        self.name = name
        self.llm = llm
        self.tools = tools
        self.prompt = hub.pull('rlm/rag-prompt') if prompt is None else prompt

    def retriever_agent(self, state: TeamFloAgentState):
        messages = state['messages']
        model = self.llm.bind_tools(self.tools)
        response = model.invoke(messages)
        # We return a list, because this will get added to the existing list
        return {'messages': [response]}

    def generate(self, state: TeamFloAgentState):
        messages = state['messages']
        question = messages[0].content
        last_message = messages[-1]

        question = messages[0].content
        docs = last_message.content

        rag_chain = self.prompt | self.llm
        response = rag_chain.invoke({'context': docs, 'question': question})
        return {'messages': [response]}

    def build(self) -> FloRag:
        retrieve = ToolNode(self.tools)

        workflow = StateGraph(TeamFloAgentState)
        workflow.add_node('agent', self.retriever_agent)
        workflow.add_node('retrieve', retrieve)  # retrieval
        workflow.add_node('generate', self.generate)
        workflow.add_conditional_edges(
            'agent',
            tools_condition,
            {
                'tools': 'retrieve',
                END: END,
            },
        )

        workflow.add_edge('retrieve', 'generate')
        workflow.add_edge('generate', END)

        workflow.set_entry_point('agent')
        graph = workflow.compile()
        return FloRag(self.name, graph=graph)
