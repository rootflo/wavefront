import functools
from flo_ai.models.flo_agent import FloAgent
from flo_ai.models.flo_routed_team import FloRoutedTeam
from langchain.agents import AgentExecutor
from flo_ai.state.flo_state import TeamFloAgentState
from langchain_core.messages import HumanMessage
from langchain_core.runnables import Runnable

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
            return {"messages": [HumanMessage(content=result["output"], name=name)]}
        
        @staticmethod
        def teamflo_tool_node(state: TeamFloAgentState, tool: Runnable, name):
            # TODO see if you want to send the entire data or not
            result = tool.invoke(state["messages"][-1])
            return {"messages": [HumanMessage(content=result, name=name)]}
        
        @staticmethod
        def get_last_message(state: TeamFloAgentState) -> str:
            return state["messages"][-1].content
        
        @staticmethod
        def join_graph(response: dict):
            return { "messages": [ response["messages"][-1] ] }
        
        @staticmethod
        def teamflo_team_node( message: str, members: list[str]):
            results = {
                "messages": [HumanMessage(content=message)],
                "team_members": ", ".join(members),
            }
            return results

        def build_from_agent(self, flo_agent: FloAgent):
            agent_func = functools.partial(FloNode.Builder.teamflo_agent_node, agent=flo_agent.executor, name=flo_agent.name)
            return FloNode(agent_func, flo_agent.name)
        
        def build_from_team(self, flo_team: FloRoutedTeam):
            return FloNode((
                FloNode.Builder.get_last_message | functools.partial(FloNode.Builder.teamflo_team_node, members=flo_team.graph.nodes)
                | flo_team.graph | FloNode.Builder.join_graph
            ), flo_team.name)
        
        # TODO add type to tool
        def build_from_tool(self, tool: Runnable, name: str):
            return FloNode(functools.partial(FloNode.Builder.teamflo_tool_node, tool=tool, name=name))