
import functools
from abc import ABC, abstractmethod
from flo_ai.state.flo_session import FloSession
from flo_ai.models.flo_member import FloMember
from flo_ai.models.flo_team import FloTeam
from flo_ai.yaml.flo_team_builder import RouterConfig
from flo_ai.models.flo_routed_team import FloRoutedTeam
from flo_ai.models.flo_agent import FloAgent
from flo_ai.state.flo_state import TeamFloAgentState
from langchain.agents import AgentExecutor
from langchain_core.messages import HumanMessage
from flo_ai.constants.prompt_constants import FLO_FINISH
from langgraph.graph import END

def teamflo_agent_node(state: TeamFloAgentState, agent: AgentExecutor, name: str):
    result = agent.invoke(state)
    return {"messages": [HumanMessage(content=result["output"], name=name)]}

class FloAgentNode:
    def __init__(self, 
                 agent_node: functools.partial, 
                 name: str) -> None:
        self.name = name
        self.agent_node = agent_node

class FloTeamChain():
    def __init__(self, name: str, chain) -> None:
        self.chain = chain
        self.name = name

# this makes it so that the states of each graph don't get intermixed
def enter_chain(message: str, members: list[str]):
    results = {
        "messages": [HumanMessage(content=message)],
        "team_members": ", ".join(members),
    }
    return results
        

class FloRouter(ABC):

    def __init__(self, session: FloSession, name: str, flo_team: FloTeam, executor, config: RouterConfig = None):
        self.router_name = name
        self.session: FloSession = session
        self.flo_team: FloTeam = flo_team
        self.members = flo_team.members
        self.member_names = [x.name for x in flo_team.members]
        self.type = flo_team.members[0].type
        self.executor = executor
        self.config = config

    def is_agent_supervisor(self):
        return self.type == "agent"
    
    def build_routed_team(self) -> FloRoutedTeam:
        if self.is_agent_supervisor():
            return self.build_agent_graph()
        else:
            return self.build_team_graph()

    @abstractmethod
    def build_agent_graph():
        pass

    @abstractmethod
    def build_team_graph():
        pass

      
    def get_last_message(self, state: TeamFloAgentState, second = None) -> str:
        return state["messages"][-1].content

    def join_graph(self, response: dict):
        return {"messages": [response["messages"][-1]]}

    def build_node(self, flo_agent: FloAgent):
        agent_func = functools.partial(teamflo_agent_node, agent=flo_agent.executor, name=flo_agent.name)
        return FloAgentNode(agent_func, flo_agent.name)
    
    def router_fn(self, state: TeamFloAgentState):
        next = state["next"]
        conditional_map = {k: k for k in self.member_names}
        conditional_map[FLO_FINISH] = END
        self.session.append(node=next)
        if self.session.is_looping(node=next):
            return conditional_map[FLO_FINISH]
        return conditional_map[next]
    
        
    def build_chain_for_teams(self, flo_team: FloRoutedTeam):
        # TODO lets see if we can convert to members
        return FloTeamChain(flo_team.name, (
            functools.partial(enter_chain, members=flo_team.graph.nodes)
            | flo_team.graph
        ))

    