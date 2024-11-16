from typing import Optional
from flo_ai.state.flo_session import FloSession
from flo_ai.yaml.config import AgentConfig
from flo_ai.models.flo_agent import FloAgent
from flo_ai.models.flo_llm_agent import FloLLMAgent
from flo_ai.models.flo_reflection_agent import FloReflectionAgent
from flo_ai.models.flo_delegation_agent import FloDelegatorAgent
from flo_ai.models.flo_tool_agent import FloToolAgent
from flo_ai.error.flo_exception import FloException
from flo_ai.models.delegate import Delegate
from flo_ai.constants.common_constants import DOCUMENTATION_AGENT_ANCHOR
from enum import Enum


class AgentKinds(Enum):
    agentic = 'agentic'
    llm = 'llm'
    tool = 'tool'
    function = 'function'
    reflection = 'reflection'
    delegator = 'delegator'


class AgentFactory:
    @staticmethod
    def create(session: FloSession, agent: AgentConfig):
        kind = agent.kind
        tool_map = session.tools
        if kind is not None:
            agent_kind = getattr(AgentKinds, kind, None)
            if agent_kind is None:
                raise FloException(f"""Unknown agent kind: `{kind}`. The supported types are llm, tool, reflection, delegator or agentic. 
                            Check the documentation @ {DOCUMENTATION_AGENT_ANCHOR}""")
            match agent_kind:
                case AgentKinds.llm:
                    return AgentFactory.__create_llm_agent(session, agent)
                case AgentKinds.tool:
                    return AgentFactory.__create_runnable_agent(session, agent)
                case AgentKinds.reflection:
                    return AgentFactory.__create_reflection_agent(session, agent)
                case AgentKinds.delegator:
                    return AgentFactory.__create_delegator_agent(session, agent)
        return AgentFactory.__create_agentic_agent(session, agent, tool_map)

    @staticmethod
    def __resolve_model(session: FloSession, model_name: Optional[str] = None):
        if model_name is None:
            return session.llm
        if model_name not in session.models:
            raise FloException(
                f"""Model not found: {model_name}.
                The model you would like to use should be registered to the session using session.register_model api, 
                and the same model name should be used here instead of `{model_name}`"""
            )
        return session.models[model_name]

    @staticmethod
    def __create_agentic_agent(
        session: FloSession, agent: AgentConfig, tool_map
    ) -> FloAgent:
        agent_model = AgentFactory.__resolve_model(session, agent.model)
        tools = [tool_map[tool.name] for tool in agent.tools]
        flo_agent: FloAgent = FloAgent.Builder(
            session,
            name=agent.name,
            job=agent.job,
            tools=tools,
            role=agent.role,
            llm=agent_model,
            on_error=session.on_agent_error,
            model_name=agent.model,
        ).build()
        return flo_agent

    @staticmethod
    def __create_llm_agent(session: FloSession, agent: AgentConfig) -> FloLLMAgent:
        agent_model = AgentFactory.__resolve_model(session, agent.model)
        builder = FloLLMAgent.Builder(
            session,
            name=agent.name,
            job=agent.job,
            role=agent.role,
            llm=agent_model,
            model_name=agent.model,
        )
        llm_agent: FloLLMAgent = builder.build()
        return llm_agent

    @staticmethod
    def __create_runnable_agent(session: FloSession, agent: AgentConfig) -> FloLLMAgent:
        runnable = session.tools[agent.tools[0].name]
        return FloToolAgent.Builder(
            session, agent.name, runnable, model_name=agent.model
        ).build()

    @staticmethod
    def __create_reflection_agent(
        session: FloSession, agent: AgentConfig
    ) -> FloReflectionAgent:
        agent_model = AgentFactory.__resolve_model(session, agent.model)
        return FloReflectionAgent.Builder(
            session,
            name=agent.name,
            job=agent.job,
            role=agent.role,
            llm=agent_model,
            to=Delegate([x.name for x in agent.to], agent.retry),
            model_name=agent.model,
        ).build()

    @staticmethod
    def __create_delegator_agent(
        session: FloSession, agent: AgentConfig
    ) -> FloReflectionAgent:
        agent_model = AgentFactory.__resolve_model(session, agent.model)
        return FloDelegatorAgent.Builder(
            session,
            agent.name,
            agent.job,
            delegate=Delegate([x.name for x in agent.to], agent.retry),
            llm=agent_model,
            model_name=agent.model,
        ).build()
