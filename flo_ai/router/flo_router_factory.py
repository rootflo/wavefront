from flo_ai.state.flo_session import FloSession
from flo_ai.router.flo_supervisor import FloSupervisor
from flo_ai.router.flo_llm_router import FloLLMRouter
from flo_ai.router.flo_linear import FloLinear
from flo_ai.yaml.config import TeamConfig
from flo_ai.models.flo_team import FloTeam
from flo_ai.router.flo_router import FloRouter
from flo_ai.router.flo_custom_router import FloCustomRouter

class FloRouterFactory:

    @staticmethod
    def create(session: FloSession, team_config: TeamConfig, flo_team: FloTeam) -> FloRouter:
        router_kind = team_config.router.kind
        if router_kind == 'supervisor':
            return FloSupervisor.Builder(session, team_config, flo_team).build()
        elif router_kind == 'linear':
            return FloLinear.Builder(session, team_config, flo_team).build()
        elif router_kind == 'llm':
            return FloLLMRouter.Builder(session, team_config, flo_team).build()
        elif router_kind == 'custom':
            return FloCustomRouter.Builder(session, team_config, flo_team).build()
        else:
            raise Exception("Unknown router type")
