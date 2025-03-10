from flo_ai.router.flo_router import FloRouter
from langgraph.graph import StateGraph, END, START
from flo_ai.state.flo_state import TeamFloAgentState
from flo_ai.models.flo_routed_team import FloRoutedTeam
from flo_ai.models.flo_team import FloTeam
from flo_ai.state.flo_session import FloSession
from flo_ai.models.flo_executable import ExecutableType


class FloLinear(FloRouter):
    def __init__(
        self,
        session: FloSession,
        name: str,
        flo_team: FloTeam,
    ):
        super().__init__(
            session=session,
            name=name,
            flo_team=flo_team,
            executor=None,
            model_name=None,
        )

    def build_graph(self):
        flo_agent_nodes = [self.build_node(member) for member in self.members]
        workflow = StateGraph(TeamFloAgentState)

        for flo_node in flo_agent_nodes:
            agent_name = flo_node.name
            workflow.add_node(agent_name, flo_node.func)

        start_node = flo_agent_nodes[0]
        end_node = flo_agent_nodes[-1]
        if start_node.kind == ExecutableType.delegator:
            next_node = (
                flo_agent_nodes[0 + 2] if (0 + 2) < len(flo_agent_nodes) else END
            )
            self.add_delegation_edge(workflow, START, start_node, next_node)
        else:
            workflow.add_edge(START, start_node.name)
        for i in range(len(flo_agent_nodes) - 1):
            parent_node = flo_agent_nodes[i]
            child_node = flo_agent_nodes[i + 1]
            next_node = (
                flo_agent_nodes[i + 2] if (i + 2) < len(flo_agent_nodes) else END
            )
            if parent_node.kind == ExecutableType.reflection:
                self.add_reflection_edge(workflow, parent_node, child_node)
                continue
            if child_node.kind == ExecutableType.delegator:
                self.add_delegation_edge(workflow, parent_node, child_node, next_node)
                continue

            if (
                child_node.kind != ExecutableType.reflection
                and parent_node.kind != ExecutableType.delegator
            ):
                workflow.add_edge(parent_node.name, child_node.name)

        if end_node.kind == ExecutableType.reflection:
            self.add_reflection_edge(workflow, end_node, END)
        elif end_node.kind != ExecutableType.delegator:
            workflow.add_edge(end_node.name, END)

        workflow_graph = workflow.compile()

        return FloRoutedTeam(self.flo_team.name, workflow_graph)

    @staticmethod
    def create(session: FloSession, name: str, team: FloTeam):
        return FloLinear.Builder(session=session, name=name, flo_team=team).build()

    class Builder:
        def __init__(
            self,
            session: FloSession,
            name: str,
            flo_team: FloTeam,
        ) -> None:
            self.name = name
            self.session = session
            self.team = flo_team

        def build(self):
            return FloLinear(self.session, self.name, self.team)
