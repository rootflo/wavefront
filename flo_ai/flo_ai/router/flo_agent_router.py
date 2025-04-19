from flo_ai.router.flo_router import FloRouter
from langgraph.graph import StateGraph, END, START
from flo_ai.state.flo_state import TeamFloAgentState
from flo_ai.models.flo_routed_team import FloRoutedTeam
from flo_ai.models.flo_base_agent import FloBaseAgent
from flo_ai.state.flo_session import FloSession


class FloAgentRouter(FloRouter):
    def __init__(
        self,
        session: FloSession,
        name: str,
        flo_agent: FloBaseAgent,
    ):
        super().__init__(
            session=session,
            name=name,
            flo_team=flo_agent,
            executor=None,
            model_name=None,
        )

    def build_graph(self):
        flo_agent_node = self.build_node(self.flo_team)
        workflow = StateGraph(TeamFloAgentState)
        workflow.add_node(self.name, flo_agent_node.func)
        workflow.add_edge(START, self.name)
        workflow.add_edge(self.name, END)

        workflow_graph = workflow.compile()
        return FloRoutedTeam(self.flo_team.name, workflow_graph)

    @staticmethod
    def create(session: FloSession, name: str, agent: FloBaseAgent):
        return FloAgentRouter.Builder(
            session=session, name=name, flo_agent=agent
        ).build()

    class Builder:
        def __init__(
            self,
            session: FloSession,
            name: str,
            flo_agent: FloBaseAgent,
        ) -> None:
            self.name = name
            self.session = session
            self.agent = flo_agent

        def build(self):
            return FloAgentRouter(self.session, self.name, self.agent)
