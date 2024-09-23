import functools
from flo_ai.models.flo_agent import FloAgent
from flo_ai.models.flo_routed_team import FloRoutedTeam
from langchain.agents import AgentExecutor
from flo_ai.state.flo_state import TeamFloAgentState, STATE_NAME_MESSAGES
from langchain_core.messages import HumanMessage
from flo_ai.yaml.config import AgentConfig, TeamConfig
from flo_ai.models.flo_executable import ExecutableType
from typing import Union

class FloNode():

    def __init__(self, 
                 func: functools.partial, 
                 name: str,
                 kind: ExecutableType,
                 config: Union[AgentConfig | TeamConfig]) -> None:
        self.name = name
        self.func = func
        self.kind: ExecutableType = kind
        self.config: Union[AgentConfig | TeamConfig] = config

    class Builder():

        def build_from_agent(self, flo_agent: FloAgent) -> 'FloNode':
            agent_func = functools.partial(FloNode.Builder.__teamflo_agent_node, agent=flo_agent.runnable, name=flo_agent.name, agent_config=flo_agent.config)
            return FloNode(agent_func, flo_agent.name, flo_agent.type, flo_agent.config)
        
        def build_from_team(self, flo_team: FloRoutedTeam) -> 'FloNode':
            team_chain = (functools.partial(FloNode.Builder.__teamflo_team_node, members=flo_team.runnable.nodes) | flo_team.runnable)
            return FloNode((
                FloNode.Builder.__get_last_message | team_chain | FloNode.Builder.__join_graph
            ), flo_team.name, flo_team.type, flo_team.config)

        @staticmethod
        def __teamflo_agent_node(state: TeamFloAgentState, agent: AgentExecutor, name: str, agent_config: AgentConfig):
            result = agent.invoke(state)
            # TODO see how to fix this
            output = result if isinstance(result, str) else result["output"]
            return { STATE_NAME_MESSAGES: [HumanMessage(content=output, name=name)] }

        @staticmethod
        def __get_last_message(state: TeamFloAgentState) -> str:
            return state[STATE_NAME_MESSAGES][-1].content
        
        @staticmethod
        def __join_graph(response: dict):
            return { STATE_NAME_MESSAGES: [ response[STATE_NAME_MESSAGES][-1] ] }
        
        @staticmethod
        def __teamflo_team_node(message: str, members: list[str]):
            results = {
                STATE_NAME_MESSAGES: [HumanMessage(content=message)],
                "team_members": ", ".join(members),
            }
            return results
