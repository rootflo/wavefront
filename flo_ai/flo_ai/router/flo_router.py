import functools
from typing import Union
from abc import ABC, abstractmethod
from langgraph.graph import END, StateGraph
from flo_ai.models.flo_node import FloNode
from flo_ai.state.flo_session import FloSession
from flo_ai.models.flo_team import FloTeam
from flo_ai.models.flo_member import FloMember
from flo_ai.models.flo_routed_team import FloRoutedTeam
from flo_ai.constants.prompt_constants import FLO_FINISH
from flo_ai.models.flo_executable import ExecutableType
from flo_ai.state.flo_state import (
    TeamFloAgentState,
    STATE_NAME_LOOP_CONTROLLER,
    STATE_NAME_NEXT,
)
from flo_ai.constants.flo_node_contants import (
    INTERNAL_NODE_REFLECTION_MANAGER,
    INTERNAL_NODE_DELEGATION_MANAGER,
)


class FloRouter(ABC):
    def __init__(
        self,
        session: FloSession,
        name: str,
        flo_team: FloTeam,
        executor,
        model_name: Union[str, None] = 'default',
    ):
        self.name = name
        self.session: FloSession = session
        self.flo_team: FloTeam = flo_team
        self.members = flo_team.members
        self.member_names = [x.name for x in flo_team.members]
        self.type: ExecutableType = ExecutableType.router
        self.executor = executor
        self.model_name = model_name

    def build_routed_team(self) -> FloRoutedTeam:
        return self.build_graph()

    @abstractmethod
    def build_graph():
        pass

    def build_node(self, flo_member: FloMember) -> FloNode:
        node_builder = FloNode.Builder(self.session)
        if flo_member.type == ExecutableType.router:
            return node_builder.build_from_router(flo_member)
        if flo_member.type == ExecutableType.team:
            return node_builder.build_from_team(flo_member)
        if flo_member.type == ExecutableType.delegator:
            return node_builder.build_from_delegator(flo_member)
        if flo_member.type == ExecutableType.reflection:
            return node_builder.build_from_reflection(flo_member)
        return node_builder.build_from_agent(flo_member)

    def router_fn(self, state: TeamFloAgentState):
        next = state['next']
        conditional_map = {k: k for k in self.member_names}
        conditional_map[FLO_FINISH] = END
        self.session.append(node=next)
        if self.session.is_looping(node=next):
            return conditional_map[FLO_FINISH]
        return conditional_map[next]

    def update_reflection_state(
        self, state: TeamFloAgentState, reflection_agent_name: str
    ):
        tracker = state.get(STATE_NAME_LOOP_CONTROLLER) or {}
        tracker[reflection_agent_name] = tracker.get(reflection_agent_name, 0) + 1
        return {STATE_NAME_LOOP_CONTROLLER: tracker}

    def add_delegation_edge(
        self,
        workflow: StateGraph,
        parent: FloNode,
        delegation_node: FloNode,
        nextNode: Union[FloNode, str],
    ):
        to_agent_names = delegation_node.delegate.to
        delegation_node_name = delegation_node.name
        next_node_name = nextNode if isinstance(nextNode, str) else nextNode.name

        retry = delegation_node.delegate.retry or 0

        conditional_map = {}
        for agent_name in to_agent_names:
            conditional_map[agent_name] = agent_name
        conditional_map[next_node_name] = next_node_name

        parent_name = parent if isinstance(parent, str) else parent.name
        if retry == 0:
            # no need to track loops when the retry is zero
            workflow.add_node(
                INTERNAL_NODE_DELEGATION_MANAGER,
                functools.partial(
                    self.update_reflection_state,
                    reflection_agent_name=delegation_node_name,
                ),
            )
            workflow.add_edge(parent_name, INTERNAL_NODE_DELEGATION_MANAGER)
            workflow.add_conditional_edges(
                INTERNAL_NODE_DELEGATION_MANAGER,
                self.__get_refelection_routing_fn(
                    retry, delegation_node_name, next_node_name
                ),
                {
                    delegation_node_name: delegation_node_name,
                    next_node_name: next_node_name,
                },
            )
        else:
            workflow.add_edge(parent_name, delegation_node_name)

        workflow.add_conditional_edges(
            delegation_node_name,
            FloRouter.__get_delegation_router_fn(next_node_name),
            conditional_map,
        )

    @staticmethod
    def __get_delegation_router_fn(nextNode: str):
        def delegation_router(state: TeamFloAgentState):
            if STATE_NAME_NEXT not in state:
                return nextNode
            return state[STATE_NAME_NEXT]

        return delegation_router

    def add_reflection_edge(
        self,
        workflow: StateGraph,
        reflection_node: FloNode,
        nextNode: Union[FloNode, str],
    ):
        to_agent_name = reflection_node.delegate.to[0]
        retry = reflection_node.delegate.retry or 1
        reflection_agent_name = reflection_node.name
        next = nextNode if isinstance(nextNode, str) else nextNode.name

        workflow.add_node(
            INTERNAL_NODE_REFLECTION_MANAGER,
            functools.partial(
                self.update_reflection_state,
                reflection_agent_name=reflection_agent_name,
            ),
        )

        workflow.add_edge(to_agent_name, INTERNAL_NODE_REFLECTION_MANAGER)
        workflow.add_conditional_edges(
            INTERNAL_NODE_REFLECTION_MANAGER,
            self.__get_refelection_routing_fn(retry, reflection_agent_name, next),
            {reflection_agent_name: reflection_agent_name, next: next},
        )
        workflow.add_edge(reflection_agent_name, to_agent_name)

    @staticmethod
    def __get_refelection_routing_fn(
        retries: int, reflection_agent_name, next_node_name
    ):
        def reflection_routing_fn(state: TeamFloAgentState):
            tracker = state[STATE_NAME_LOOP_CONTROLLER]
            if (
                tracker is not None
                and reflection_agent_name in tracker
                and tracker[reflection_agent_name] > retries
            ):
                return next_node_name
            return reflection_agent_name

        return reflection_routing_fn
