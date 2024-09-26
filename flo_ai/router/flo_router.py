
from abc import ABC, abstractmethod
from flo_ai.state.flo_session import FloSession
from flo_ai.models.flo_team import FloTeam
from flo_ai.yaml.config import TeamConfig
from flo_ai.models.flo_routed_team import FloRoutedTeam
from flo_ai.models.flo_agent import FloAgent
from flo_ai.state.flo_state import TeamFloAgentState, STATE_NAME_LOOP_CONTROLLER, STATE_NAME_NEXT
from flo_ai.models.flo_node import FloNode
from flo_ai.constants.prompt_constants import FLO_FINISH
from langgraph.graph import END,StateGraph
from flo_ai.models.flo_node import FloNode
from flo_ai.models.flo_executable import ExecutableType
import functools
from typing import Union
from flo_ai.constants.flo_node_contants import (INTERNAL_NODE_REFLECTION_MANAGER, INTERNAL_NODE_DELEGATION_MANAGER)


class FloRouter(ABC):

    def __init__(self, session: FloSession, name: str, flo_team: FloTeam, executor, config: TeamConfig = None):
        self.router_name = name
        self.session: FloSession = session
        self.flo_team: FloTeam = flo_team
        self.members = flo_team.members
        self.member_names = [x.name for x in flo_team.members]
        self.type: ExecutableType = flo_team.members[0].type
        self.executor = executor
        self.config = config

    def is_agent_supervisor(self):
        return ExecutableType.isAgent(self.type)
    
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

    def build_node(self, flo_agent: FloAgent) -> FloNode:
        if (flo_agent.type == ExecutableType.delegator):
            return FloNode(flo_agent.executor, flo_agent.name, flo_agent.type, flo_agent.config)
        node_builder = FloNode.Builder()
        return node_builder.build_from_agent(flo_agent)
    
    def router_fn(self, state: TeamFloAgentState):
        next = state["next"]
        conditional_map = {k: k for k in self.member_names}
        conditional_map[FLO_FINISH] = END
        self.session.append(node=next)
        if self.session.is_looping(node=next):
            return conditional_map[FLO_FINISH]
        return conditional_map[next]
        
    def build_node_for_teams(self, flo_team: FloRoutedTeam):
        node_builder = FloNode.Builder()
        return node_builder.build_from_team(flo_team)
    
    def update_reflection_state(self, state: TeamFloAgentState, reflection_agent_name: str):
        tracker = None
        if STATE_NAME_LOOP_CONTROLLER not in state or state[STATE_NAME_LOOP_CONTROLLER] is None:
            tracker = dict()
        else:
            tracker = state[STATE_NAME_LOOP_CONTROLLER]
      
        if reflection_agent_name in tracker:
            tracker[reflection_agent_name] += 1
        else:
            tracker[reflection_agent_name] = 1
            
        return {
            STATE_NAME_LOOP_CONTROLLER: tracker
        }
    
    def add_delegation_edge(self, workflow: StateGraph, parent: FloNode, delegation_node: FloNode, nextNode: Union[FloNode|str]):
        to_agent_names = [x.name for x in delegation_node.config.to]
        delegation_node_name = delegation_node.name
        next_node_name = nextNode if isinstance(nextNode, str) else nextNode.name
        retry = delegation_node.config.retry or 1
        
        conditional_map = {}
        for agent_name in to_agent_names:
            conditional_map[agent_name] = agent_name
        conditional_map[next_node_name] = next_node_name

        workflow.add_node(
            INTERNAL_NODE_DELEGATION_MANAGER, 
            functools.partial(
                self.update_reflection_state, 
                reflection_agent_name=delegation_node_name
            )
        )

        workflow.add_edge(parent.name, INTERNAL_NODE_DELEGATION_MANAGER)
        workflow.add_conditional_edges(
            INTERNAL_NODE_DELEGATION_MANAGER, 
            self.__get_refelection_routing_fn(retry, delegation_node_name, next_node_name), 
            { delegation_node_name: delegation_node_name, next_node_name: next_node_name}
        )

        workflow.add_conditional_edges(
            delegation_node_name, 
            FloRouter.__get_delegation_router_fn(next_node_name),
            conditional_map
        )

    @staticmethod
    def __get_delegation_router_fn(nextNode: str):
        def delegation_router(state: TeamFloAgentState):
            if STATE_NAME_NEXT not in state:
                return nextNode
            return state[STATE_NAME_NEXT]
        return delegation_router
    
    def add_reflection_edge(self, workflow: StateGraph, reflection_node: FloNode, nextNode: Union[FloNode | str]):
        to_agent_name = reflection_node.config.to[0].name
        retry = reflection_node.config.retry or 1
        reflection_agent_name = reflection_node.name
        next = nextNode if isinstance(nextNode, str) else nextNode.name
        
        workflow.add_node(INTERNAL_NODE_REFLECTION_MANAGER, functools.partial(self.update_reflection_state, reflection_agent_name=reflection_agent_name))
        
        workflow.add_edge(to_agent_name, INTERNAL_NODE_REFLECTION_MANAGER)
        workflow.add_conditional_edges(
            INTERNAL_NODE_REFLECTION_MANAGER, 
            self.__get_refelection_routing_fn(retry, reflection_agent_name, next), 
            { reflection_agent_name: reflection_agent_name,  next: next }
        )
        workflow.add_edge(reflection_agent_name, to_agent_name)

    @staticmethod
    def __get_refelection_routing_fn(retries: int, reflection_agent_name, next_node_name):
        def reflection_routing_fn(state: TeamFloAgentState):
            tracker = state[STATE_NAME_LOOP_CONTROLLER]
            if tracker is not None and reflection_agent_name in tracker and tracker[reflection_agent_name] > retries:
                return next_node_name
            return reflection_agent_name

        return reflection_routing_fn
    

    
        
    