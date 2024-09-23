from flo_ai.models.flo_team import FloTeam
from flo_ai.models.flo_agent import FloAgent
from flo_ai.yaml.config import (FloRoutedTeamConfig, TeamConfig, AgentConfig, FloAgentConfig)
from flo_ai.models.flo_executable import ExecutableFlo
from flo_ai.state.flo_session import FloSession
from flo_ai.router.flo_router_factory import FloRouterFactory
from flo_ai.factory.agent_factory import AgentFactory

def build_supervised_team(session: FloSession) -> ExecutableFlo:
    flo_config = session.config
    if isinstance(flo_config, FloRoutedTeamConfig):
        team_config: TeamConfig = flo_config.team
        team = parse_and_build_subteams(session, team_config)    
        return team
    elif isinstance(flo_config, FloAgentConfig):
        agent_config: AgentConfig = flo_config.agent
        agent = AgentFactory.create(session, agent_config)
        return agent

def parse_and_build_subteams(session: FloSession, team_config: TeamConfig) -> ExecutableFlo:
    flo_team = None
    if team_config.agents:
        members = [AgentFactory.create(session, agent) for agent in team_config.agents]
        flo_team = FloTeam.Builder(team_config, members=members).build()
        router = FloRouterFactory.create(session, team_config, flo_team)
        flo_routed_team = router.build_routed_team()
    else:
        flo_teams = []
        for subteam in team_config.subteams:
            flo_subteam = parse_and_build_subteams(session, subteam)
            flo_teams.append(flo_subteam)
        flo_team = FloTeam.Builder(team_config, members=flo_teams).build()
        router = FloRouterFactory.create(session, team_config, flo_team)
        flo_routed_team = router.build_routed_team()
    return flo_routed_team

