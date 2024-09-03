from langchain_core.output_parsers.openai_functions import JsonOutputFunctionsParser
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from typing import Union
from langchain_core.runnables import Runnable
from flo_ai.state.flo_session import FloSession
from flo_ai.constants.prompt_constants import FLO_FINISH
from flo_ai.helpers.utils import randomize_name
from flo_ai.router.flo_router import FloRouter
from flo_ai.models.flo_team import FloTeam
from flo_ai.models.flo_routed_team import FloRoutedTeam
from langgraph.graph import StateGraph
from flo_ai.state.flo_state import TeamFloAgentState


# TODO, maybe add description about what team members can do
supervisor_system_message = (
    "You are a supervisor tasked with managing a conversation between the"
    " following {member_type}: {members}. Given the following user request,"
    " respond with the worker to act next. Each worker will perform a"
    " task and respond with their results and status. When the users question is answered or the assigned task is finished,"
    " respond with FINISH. If both your workers has responded atleast once, then strictly return FINISH "
)

class StateUpdateComponent:
    def __init__(self, name: str, session: FloSession) -> None:
        self.name = name
        self.inner_session = session

    def __call__(self, input):
        self.inner_session.append(self.name)
        return input

class FloSupervisor(FloRouter):
    
    def __init__(self,
                 session: FloSession,
                 executor: Runnable, 
                 flo_team: FloTeam,
                 name: str) -> None:
        super().__init__(
            session = session, 
            name = name, 
            flo_team = flo_team,
            executor = executor
        )
    
    def build_agent_graph(self):
        flo_agent_nodes = [self.build_node(flo_agent) for flo_agent in self.members]
        workflow = StateGraph(TeamFloAgentState)
        for flo_agent_node in flo_agent_nodes:
            workflow.add_node(flo_agent_node.name, flo_agent_node.func)
        workflow.add_node(self.router_name, self.executor)
        for member in self.member_names:
            workflow.add_edge(member, self.router_name)
        workflow.add_conditional_edges(self.router_name, self.router_fn)
        workflow.set_entry_point(self.router_name)
        workflow_graph = workflow.compile()
        return FloRoutedTeam(self.flo_team.name, workflow_graph)

    def build_team_graph(self):
        flo_team_entry_chains = [self.build_node_for_teams(flo_agent) for flo_agent in self.members]
        # Define the graph.
        super_graph = StateGraph(TeamFloAgentState)
        # First add the nodes, which will do the work
        for flo_team_chain in flo_team_entry_chains:
            super_graph.add_node(flo_team_chain.name, flo_team_chain.func)
        super_graph.add_node(self.router_name, self.executor)

        for member in self.member_names:
            super_graph.add_edge(member, self.router_name)

        super_graph.add_conditional_edges(self.router_name, self.router_fn)

        super_graph.set_entry_point(self.router_name)
        super_graph = super_graph.compile()
        return FloRoutedTeam(self.flo_team.name, super_graph)

class FloSupervisorBuilder:
    def __init__(self,
                 session: FloSession,
                 name: str,
                 flo_team: FloTeam,
                 supervisor_prompt: Union[ChatPromptTemplate, None] = None,
                 llm: Union[BaseLanguageModel, None] = None) -> None:
        # TODO add validation for reporteess
        self.name = randomize_name(name)
        self.session = session
        self.llm = llm if llm is not None else session.llm
        self.flo_team = flo_team
        self.agents = flo_team.members
        self.members = [agent.name for agent in flo_team.members]
        self.options = self.members + [FLO_FINISH]
        member_type = "workers" if flo_team.members[0].type == "agent" else "team members"
        self.supervisor_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", supervisor_system_message),
                MessagesPlaceholder(variable_name="messages"),
                (
                    "system",
                    "Given the conversation above, who should act next?"
                    " Or should we FINISH if the task is already answered, (do not wait for the entire question to be answered) or there isn't enough information to answer the question, even then return FINISH? Select one of: {options}",
                ),
            ]
        ).partial(options=str(self.options), members=", ".join(self.members), member_type=member_type) if supervisor_prompt is None else  supervisor_prompt
    
    def build(self):
        function_def = {
            "name": "route",
            "description": "Select the next role.",
            "parameters": {
                "title": "routeSchema",
                "type": "object",
                "properties": {
                    "next": {
                        "title": "Next",
                        "anyOf": [
                            {"enum": self.options},
                        ],
                    }
                },
                "required": ["next"],
            }
        }
            
        chain = (
            self.supervisor_prompt
            | self.llm.bind_functions(functions=[function_def], function_call="route")
            | JsonOutputFunctionsParser()
            | StateUpdateComponent(self.name, self.session)
        )

        return FloSupervisor(executor = chain, 
                             flo_team=self.flo_team, 
                             name=self.name, 
                             session=self.session)