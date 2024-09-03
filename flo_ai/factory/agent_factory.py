from flo_ai.state.flo_session import FloSession
from flo_ai.yaml.flo_team_builder import (AgentConfig)
from flo_ai.models.flo_agent import FloAgent
from flo_ai.models.flo_llm_agent import FloLLMAgent
from flo_ai.models.flo_executable import ExecutableFlo
from enum import Enum

class AgentKinds(Enum):
    agentic = "agentic"
    llm = "llm"
    tool = "tool"
    function = "function"

class AgentFactory():

    @staticmethod
    def create(session: FloSession, agent: AgentConfig, tool_map):
        kind = agent.kind
        if kind is not None:
            agent_kind = getattr(AgentKinds, kind, None)
            if agent_kind is None:
                raise ValueError(f"Agent kind cannot be {kind} !")
            match(agent_kind):
                case AgentKinds.llm:
                    return AgentFactory.__create_llm_agent(session, agent)
                case AgentKinds.tool:
                    return AgentFactory.__create_runnable_agent(session, agent)
        return AgentFactory.__create_agentic_agent(session, agent, tool_map)

    @staticmethod
    def __create_agentic_agent(session: FloSession, agent: AgentConfig, tool_map) -> FloAgent:
        tools = [tool_map[tool.name] for tool in agent.tools]
        flo_agent: FloAgent = FloAgent.Builder(
            session,
            agent.name, 
            agent.job,
            tools
        ).build()
        return flo_agent

    @staticmethod
    def __create_llm_agent(session: FloSession, agent: AgentConfig) -> FloLLMAgent:
        builder = FloLLMAgent.Builder(session, agent.name, agent.job, agent.role)
        llm_agent: FloLLMAgent = builder.build()
        return llm_agent
    
    @staticmethod
    def __create_runnable_agent(session: FloSession, agent: AgentConfig) -> FloLLMAgent:
        runnable = session.tools[agent.tools[0].name]
        return ExecutableFlo(agent.name, runnable, "agent")