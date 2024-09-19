import functools
from flo_ai.models.flo_agent import FloAgent
from flo_ai.models.flo_routed_team import FloRoutedTeam
from langchain.agents import AgentExecutor
from flo_ai.state.flo_state import TeamFloAgentState
from langchain_core.messages import HumanMessage

class FloNode():

    def __init__(self, 
                 func: functools.partial, 
                 name: str) -> None:
        self.name = name
        self.func = func

    class Builder():

        @staticmethod
        def teamflo_agent_node(state: TeamFloAgentState, agent: AgentExecutor, name: str):
            result = agent.invoke(state)
            # TODO see how to fix this
            output = result if isinstance(result, str) else result["output"]
            return { "messages": [HumanMessage(content=output, name=name)] }

        @staticmethod
        def get_last_message(state: TeamFloAgentState) -> str:
            return state["messages"][-1].content
        
        @staticmethod
        def join_graph(response: dict):
            return { "messages": [ response["messages"][-1] ] }
        
        @staticmethod
        def teamflo_team_node(message: str, members: list[str]):
            results = {
                "messages": [HumanMessage(content=message)],
                "team_members": ", ".join(members),
            }
            return results

        def build_from_agent(self, flo_agent: FloAgent):
            agent_func = functools.partial(FloNode.Builder.teamflo_agent_node, agent=flo_agent.executor, name=flo_agent.name)
            return FloNode(agent_func, flo_agent.name)
        
        def build_from_team(self, flo_team: FloRoutedTeam):
            team_chain = (functools.partial(FloNode.Builder.teamflo_team_node, members=flo_team.runnable.nodes) | flo_team.runnable)
            return FloNode((
                FloNode.Builder.get_last_message | team_chain | FloNode.Builder.join_graph
            ), flo_team.name)