import functools
from flo_ai.models.flo_agent import FloAgent
from flo_ai.models.flo_reflection_agent import FloReflectionAgent
from flo_ai.models.flo_routed_team import FloRoutedTeam
from flo_ai.models.delegate import Delegate
from langchain.agents import AgentExecutor
from flo_ai.state.flo_state import TeamFloAgentState, STATE_NAME_MESSAGES
from langchain_core.messages import HumanMessage
from flo_ai.models.flo_executable import ExecutableType
from flo_ai.state.flo_session import FloSession
from typing import Optional, Type, List
from flo_ai.callbacks.flo_callbacks import (
    FloAgentCallback,
    FloRouterCallback,
    FloCallback,
)


class FloNode:
    def __init__(
        self,
        func: functools.partial,
        name: str,
        kind: ExecutableType,
        delegate: Optional[Delegate] = None,
    ) -> None:
        self.name = name
        self.func = func
        self.kind: ExecutableType = kind
        self.delegate = delegate

    class Builder:
        def __init__(self, session: FloSession) -> None:
            self.session = session

        def build_from_agent(self, flo_agent: FloAgent) -> 'FloNode':
            agent_func = functools.partial(
                FloNode.Builder.__teamflo_agent_node,
                agent=flo_agent.runnable,
                name=flo_agent.name,
                session=self.session,
                model_name=flo_agent.model_name,
            )
            return FloNode(agent_func, flo_agent.name, flo_agent.type)

        def build_from_reflection(self, flo_agent: FloReflectionAgent) -> 'FloNode':
            agent_func = functools.partial(
                FloNode.Builder.__teamflo_agent_node,
                agent=flo_agent.runnable,
                name=flo_agent.name,
                session=self.session,
                model_name=flo_agent.model_name,
            )
            return FloNode(
                agent_func, flo_agent.name, flo_agent.type, delegate=flo_agent.delegate
            )

        def build_from_team(self, flo_team: FloRoutedTeam) -> 'FloNode':
            team_chain = (
                functools.partial(
                    FloNode.Builder.__teamflo_team_node, members=flo_team.runnable.nodes
                )
                | flo_team.runnable
            )
            return FloNode(
                (
                    FloNode.Builder.__get_last_message
                    | team_chain
                    | FloNode.Builder.__join_graph
                ),
                flo_team.name,
                flo_team.type,
            )

        def build_from_router(self, flo_router) -> 'FloNode':
            router_func = functools.partial(
                FloNode.Builder.__teamflo_router_node,
                agent=flo_router.executor,
                name=flo_router.name,
                session=self.session,
                model_name=flo_router.model_name,
            )
            return FloNode(router_func, flo_router.name, flo_router.type)

        def build_from_delegator(self, flo_router) -> 'FloNode':
            router_func = functools.partial(
                FloNode.Builder.__teamflo_router_node,
                agent=flo_router.executor,
                name=flo_router.name,
                session=self.session,
                model_name=flo_router.model_name,
            )
            return FloNode(
                router_func,
                flo_router.name,
                flo_router.type,
                delegate=flo_router.delegate,
            )

        @staticmethod
        def __teamflo_agent_node(
            state: TeamFloAgentState,
            agent: AgentExecutor,
            name: str,
            session: FloSession,
            model_name: str,
        ):
            agent_cbs: List[FloAgentCallback] = FloNode.Builder.__filter_callbacks(
                session, FloAgentCallback
            )
            flo_cbs: List[FloCallback] = FloNode.Builder.__filter_callbacks(
                session, FloCallback
            )
            [
                callback.on_agent_start(name, model_name, state['messages'], **{})
                for callback in agent_cbs
            ]
            [
                callback.on_agent_start(name, model_name, state['messages'], **{})
                for callback in flo_cbs
            ]
            try:
                result = agent.invoke(state)
                output = result if isinstance(result, str) else result['output']
            except Exception as e:
                [
                    callback.on_agent_error(name, model_name, e, **{})
                    for callback in agent_cbs
                ]
                [
                    callback.on_agent_error(name, model_name, e, **{})
                    for callback in flo_cbs
                ]
                raise e
            [
                callback.on_agent_end(name, model_name, output, **{})
                for callback in agent_cbs
            ]
            [
                callback.on_agent_start(name, model_name, output, **{})
                for callback in flo_cbs
            ]
            return {STATE_NAME_MESSAGES: [HumanMessage(content=output, name=name)]}

        @staticmethod
        def __filter_callbacks(session: FloSession, type: Type):
            cbs = session.callbacks
            return list(filter(lambda callback: isinstance(callback, type), cbs))

        @staticmethod
        def __teamflo_router_node(
            state: TeamFloAgentState,
            agent: AgentExecutor,
            name: str,
            session: FloSession,
            model_name: str,
        ):
            agent_cbs: List[FloRouterCallback] = FloNode.Builder.__filter_callbacks(
                session, FloRouterCallback
            )
            flo_cbs: List[FloCallback] = FloNode.Builder.__filter_callbacks(
                session, FloCallback
            )
            [
                callback.on_router_start(name, model_name, state['messages'], **{})
                for callback in agent_cbs
            ]
            [
                callback.on_router_start(name, model_name, state['messages'], **{})
                for callback in flo_cbs
            ]
            try:
                result = agent.invoke(state)
                nextNode = result if isinstance(result, str) else result['next']
            except Exception as e:
                [
                    callback.on_router_error(name, model_name, e, **{})
                    for callback in agent_cbs
                ]
                [
                    callback.on_router_error(name, model_name, e, **{})
                    for callback in flo_cbs
                ]
                raise e
            [
                callback.on_router_end(name, model_name, nextNode, **{})
                for callback in agent_cbs
            ]
            [
                callback.on_router_start(name, model_name, nextNode, **{})
                for callback in flo_cbs
            ]
            return {'next': nextNode}

        @staticmethod
        def __get_last_message(state: TeamFloAgentState) -> str:
            return state[STATE_NAME_MESSAGES][-1].content

        @staticmethod
        def __join_graph(response: dict):
            return {STATE_NAME_MESSAGES: [response[STATE_NAME_MESSAGES][-1]]}

        @staticmethod
        def __teamflo_team_node(message: str, members: list[str]):
            results = {
                STATE_NAME_MESSAGES: [HumanMessage(content=message)],
                'team_members': ', '.join(members),
            }
            return results
