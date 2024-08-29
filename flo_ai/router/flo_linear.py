from flo_ai.yaml.flo_team_builder import RouterConfig
from flo_ai.models.flo_member import FloMember

class FloLinear:
    def __init__(self, agents: list[FloMember], config: RouterConfig):
        self.agents = agents
        self.name = config.name
        self.config: RouterConfig = config
        self.type = agents[0].type

    def is_agent_supervisor(self):
        return self.type == "agent"
