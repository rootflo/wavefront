from flo_ai.models.flo_team import FloTeamBuilder
from flo_ai.models.flo_agent import FloAgent
from flo_ai.yaml.flo_team_builder import (FloRoutedTeamConfig, TeamConfig,
                                        AgentConfig, FloAgentConfig)
from flo_ai.models.flo_executable import ExecutableFlo
from flo_ai.models.flo_planner import FloPlannerBuilder
from flo_ai.state.flo_session import FloSession
from flo_ai.router.flo_router_factory import FloRouterFactory
from flo_ai.factory.agent_factory import AgentFactory
from typing import Union

def build_supervised_team(
        session: FloSession,
        flo_config: Union[FloRoutedTeamConfig, FloAgentConfig]) -> ExecutableFlo:
    if isinstance(flo_config, FloRoutedTeamConfig):
        team_config: TeamConfig = flo_config.team
        team = parse_and_build_subteams(session, team_config, session.tools)    
        return team
    elif isinstance(flo_config, FloAgentConfig):
        agent_config: AgentConfig = flo_config.agent
        agent = AgentFactory.create(session, agent_config, session.tools)
        return agent

def parse_and_build_subteams(
        session: FloSession,
        team_config: TeamConfig,
        tool_map) -> ExecutableFlo:
    flo_team = None
    if team_config.agents:
        agents = []
        for agent in team_config.agents:
            flo_agent: FloAgent = AgentFactory.create(session, agent, tool_map)
            agents.append(flo_agent)
        flo_team = FloTeamBuilder(
            session=session,
            name=team_config.name,
            members=agents
        ).build()
        router = FloRouterFactory.create(session, team_config, flo_team)
        flo_routed_team = router.build_routed_team()
        if team_config.planner is not None:
            return FloPlannerBuilder(session, team_config.planner.name, flo_routed_team).build()
    else:
        flo_teams = []
        for subteam in team_config.subteams:
            flo_subteam = parse_and_build_subteams(session, subteam, tool_map)
            flo_teams.append(flo_subteam)
        flo_team = FloTeamBuilder(
            session=session,
            name=team_config.name,
            members=flo_teams
        ).build()
        router = FloRouterFactory.create(session, team_config, flo_team)
        flo_routed_team = router.build_routed_team()
    return flo_routed_team

