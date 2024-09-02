from flo_ai.state.flo_session import FloSession
from flo_ai.router.flo_supervisor import FloSupervisorBuilder
from flo_ai.router.flo_linear import FloLinear
from flo_ai.yaml.flo_team_builder import TeamConfig
from flo_ai.models.flo_team import FloTeam
from flo_ai.router.flo_router import FloRouter

class FloRouterFactory:

    @staticmethod
    def create(session: FloSession, team_config: TeamConfig, flo_team: FloTeam) -> FloRouter:
        if team_config.router.kind == 'supervisor':
            return FloSupervisorBuilder(session, team_config.router.name, flo_team).build()
        elif team_config.router.kind == 'linear':
            return FloLinear(session, flo_team, team_config.router)
        else:
            raise Exception("Unknown router type")
