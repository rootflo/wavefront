from pydantic import BaseModel
from typing import List, Union, Dict, Any
import yaml
import re
from typing import Optional
from flo_ai.models.exception import FloValidationException


KIND_SUPERVISED_TEAM = 'FloRoutedTeam'
KIND_FLO_AGENT = 'FloAgent'

yaml_kinds = [KIND_SUPERVISED_TEAM, KIND_FLO_AGENT]


class KeyValueArgs(BaseModel):
    name: str
    value: str


class FilterArgs(BaseModel):
    name: str
    description: str
    type: str


class ToolConfig(BaseModel):
    name: str
    args: Optional[List[KeyValueArgs]] = None
    properties: Optional[List[KeyValueArgs]] = None
    filters: Optional[List[FilterArgs]] = None


class MemberKey(BaseModel):
    name: str


class Parser(BaseModel):
    name: str
    fields: Optional[List[Dict[str, Any]]] = None


class AgentConfig(BaseModel):
    name: str
    role: Optional[str] = None
    kind: Optional[str] = None
    job: Optional[str] = None
    tools: List[ToolConfig] = []
    to: Optional[List[MemberKey]] = None
    retry: Optional[int] = 1
    model: Optional[str] = None
    parser: Union[Parser, str] = None
    data_collector: Optional[str] = None


class EdgeConfig(BaseModel):
    edge: List[str]
    type: Optional[str] = None
    rule: Optional[str] = None


class RouterConfig(BaseModel):
    name: str
    kind: str
    model: Optional[str] = None
    job: Optional[str] = None
    start_node: Optional[str] = None
    end_node: Union[Optional[str], List[str]] = None
    edges: Optional[List[EdgeConfig]] = None


class PlannerConfig(BaseModel):
    name: str


class TeamConfig(BaseModel):
    name: str
    kind: Optional[str] = None
    agents: Optional[List[AgentConfig]] = None
    subteams: Optional[List['TeamConfig']] = None
    router: Optional[RouterConfig] = None
    planner: Optional[PlannerConfig] = None


class FloRoutedTeamConfig(BaseModel):
    apiVersion: str
    kind: str
    name: str
    team: TeamConfig


class FloAgentConfig(BaseModel):
    apiVersion: str
    kind: Optional[str] = None
    name: str
    agent: AgentConfig


def to_supervised_team(yaml_str: str) -> FloRoutedTeamConfig:
    parsed_data = yaml.safe_load(yaml_str)
    kind = parsed_data['kind']
    if kind == KIND_SUPERVISED_TEAM:
        flo_supervised_team = FloRoutedTeamConfig(**parsed_data)
        validate_sup_team_config(flo_supervised_team)
        return flo_supervised_team
    elif kind == KIND_FLO_AGENT:
        flo_agent = FloAgentConfig(**parsed_data)
        validate_sup_team_config(flo_agent)
        return flo_agent
    else:
        raise FloValidationException('Unknown kind: {}'.format(kind))


def validate_sup_team_config(flo: FloRoutedTeamConfig):
    if flo.kind == KIND_FLO_AGENT:
        return
    if flo.name is None or not is_valid_name(flo.name):
        raise FloValidationException(
            'Invalid agent name while creating the flow, expected: [^[a-z][a-z0-9_-]*$]'
        )


def is_valid_name(s: str) -> bool:
    pattern = r'^[a-z][a-z0-9_-]*$'
    return bool(re.match(pattern, s))
