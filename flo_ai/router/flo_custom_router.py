from flo_ai.yaml.config import TeamConfig
from flo_ai.router.flo_router import FloRouter
from langgraph.graph import StateGraph, END, START
from flo_ai.state.flo_state import TeamFloAgentState
from flo_ai.models.flo_routed_team import FloRoutedTeam
from flo_ai.models.flo_team import FloTeam
from flo_ai.state.flo_session import FloSession
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers.openai_functions import JsonOutputFunctionsParser

class FloCustomRouter(FloRouter):

    def __init__(self, session: FloSession, config: TeamConfig, flo_team: FloTeam):
        self.llm = session.llm
        super().__init__(session=session, name=config.name,
                          flo_team=flo_team, executor=None, config=config)
        self.router_config = config.router
    
    def build_router_fn(self, members, rule):
        def router_fn(state: TeamFloAgentState):
            conditional_map = {k: k for k in members}
            
            prompt = ChatPromptTemplate.from_messages(
            [
                MessagesPlaceholder(variable_name="messages"),
                (
                    "system",
                    "Given the conversation above, who should act next? Select one of: {members}. The rule is given below:"
                ),
                ('system', rule)
            ]
            ).partial(members=", ".join(members))


            function_def = {
                "name": "route",
                "description": "Select the next role.",
                "parameters": {
                    "title": "routeSchema",
                    "type": "object",
                    "properties": {
                        "next": {
                            "title": "Next",
                            "anyOf": [
                                {"enum": members},
                            ],
                        }
                    },
                    "required": ["next"],
                }
            }

            chain = prompt | self.llm.bind_functions(functions=[function_def], function_call="route") | JsonOutputFunctionsParser()
            output = chain.invoke(state)

            next = output['next']
            state['next'] = next
            
            return conditional_map[next] 
        
        return router_fn
    
    def build_graph(self):
        flo_agent_nodes = [self.build_node(flo_agent) for flo_agent in self.members]
        workflow = StateGraph(TeamFloAgentState)
        
        for flo_agent_node in flo_agent_nodes:
            agent_name = flo_agent_node.name
            workflow.add_node(agent_name, flo_agent_node.func)

        router_config = self.router_config
        workflow.add_edge(START, router_config.start_node)
        for edge_config in router_config.edges:
            edge = edge_config.edge
            if len(edge) > 2:
                if edge_config.type == 'conditional_llm':
                    members = edge[1:]
                    router = self.build_router_fn(members, edge_config.rule)
                    workflow.add_conditional_edges(edge[0], router, {item: item for item in members})
            else:
                workflow.add_edge(edge[0], edge[1])

        if isinstance(router_config.end_node, list):    
            for node in router_config.end_node:
                workflow.add_edge(node, END)
        else:
            workflow.add_edge(router_config.end_node, END)

        workflow_graph = workflow.compile()

        return FloRoutedTeam(self.flo_team.name, workflow_graph, self.flo_team.config)

    class Builder():

        def __init__(self, session: FloSession, config: TeamConfig, flo_team: FloTeam,) -> None:
            self.session = session
            self.config = config
            self.team = flo_team

        def build(self):
            return FloCustomRouter(self.session, self.config, self.team, )