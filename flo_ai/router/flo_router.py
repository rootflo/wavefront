
from typing import Union, List
from flo_ai.state.flo_session import FloSession
from flo_ai.router.flo_supervisor import FloSupervisorBuilder, FloSupervisor
from flo_ai.router.flo_linear import FloLinear
from flo_ai.yaml.flo_team_builder import TeamConfig
from flo_ai.models.flo_member import FloMember

class FloRouter:
    def __init__(self, kind, router):
        self.kind: str = kind
        self.output: Union[FloSupervisor, FloLinear] = router


class FloRouterBuilder:
    def __init__(self,
                session: FloSession,
                team_config: TeamConfig,
                agents: list[FloMember]
            ) -> None:
        self.session = session
        self.team_config = team_config
        self.agents = agents

    
    def build(self) -> FloRouter:
        if self.team_config.router.kind == 'supervisor':
            router = FloSupervisorBuilder(self.session, self.team_config.router, self.agents).build()
        elif self.team_config.router.kind == 'linear':
            router = FloLinear(self.agents, self.team_config.router)
        else:
            raise Exception("Unknown router type")
    
        return FloRouter(self.team_config.router.kind, router)
