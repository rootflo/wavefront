from typing import List, Optional, Callable, Union, Dict, Any
from flo_ai.arium.arium import Arium
from flo_ai.arium.memory import MessageMemory, BaseMemory
from flo_ai.models.agent import Agent
from flo_ai.tool.base_tool import Tool
from flo_ai.llm.base_llm import ImageMessage


class AriumBuilder:
    """
    A builder class for creating and configuring Arium instances with a fluent interface.

    Example usage:
        result = (AriumBuilder()
                  .with_memory(my_memory)
                  .add_agent(agent1)
                  .add_tool(tool1)
                  .start_with(agent1)
                  .add_edge(agent1, [tool1], router_fn)
                  .end_with(tool1)
                  .build_and_run(["Hello, world!"]))
    """

    def __init__(self):
        self._memory: Optional[BaseMemory] = None
        self._agents: List[Agent] = []
        self._tools: List[Tool] = []
        self._start_node: Optional[Union[Agent, Tool]] = None
        self._end_nodes: List[Union[Agent, Tool]] = []
        self._edges: List[tuple] = []  # (from_node, to_nodes, router)
        self._arium: Optional[Arium] = None

    def with_memory(self, memory: BaseMemory) -> 'AriumBuilder':
        """Set the memory for the Arium."""
        self._memory = memory
        return self

    def add_agent(self, agent: Agent) -> 'AriumBuilder':
        """Add an agent to the Arium."""
        self._agents.append(agent)
        return self

    def add_agents(self, agents: List[Agent]) -> 'AriumBuilder':
        """Add multiple agents to the Arium."""
        self._agents.extend(agents)
        return self

    def add_tool(self, tool: Tool) -> 'AriumBuilder':
        """Add a tool to the Arium."""
        self._tools.append(tool)
        return self

    def add_tools(self, tools: List[Tool]) -> 'AriumBuilder':
        """Add multiple tools to the Arium."""
        self._tools.extend(tools)
        return self

    def start_with(self, node: Union[Agent, Tool]) -> 'AriumBuilder':
        """Set the starting node for the Arium."""
        self._start_node = node
        return self

    def end_with(self, node: Union[Agent, Tool]) -> 'AriumBuilder':
        """Add an ending node to the Arium."""
        if node not in self._end_nodes:
            self._end_nodes.append(node)
        return self

    def add_edge(
        self,
        from_node: Union[Agent, Tool],
        to_nodes: List[Union[Agent, Tool]],
        router: Optional[Callable] = None,
    ) -> 'AriumBuilder':
        """Add an edge between nodes with an optional router function."""
        self._edges.append((from_node, to_nodes, router))
        return self

    def connect(
        self,
        from_node: Union[Agent, Tool],
        to_node: Union[Agent, Tool],
    ) -> 'AriumBuilder':
        """Simple connection between two nodes without a router."""
        return self.add_edge(from_node, [to_node])

    def build(self) -> Arium:
        """Build the Arium instance from the configured components."""
        # Use default memory if none provided
        if self._memory is None:
            self._memory = MessageMemory()

        # Create Arium instance
        arium = Arium(self._memory)

        # Add all nodes
        all_nodes = []
        all_nodes.extend(self._agents)
        all_nodes.extend(self._tools)

        if not all_nodes:
            raise ValueError('No agents or tools added to the Arium')

        arium.add_nodes(all_nodes)

        # Set start node
        if self._start_node is None:
            raise ValueError(
                'No start node specified. Use start_with() to set a start node.'
            )

        arium.start_at(self._start_node)

        # Add edges
        for from_node, to_nodes, router in self._edges:
            arium.add_edge(from_node.name, [node.name for node in to_nodes], router)

        # Add end nodes
        if not self._end_nodes:
            raise ValueError('No end nodes specified. Use end_with() to add end nodes.')

        for end_node in self._end_nodes:
            arium.add_end_to(end_node)

        # Compile the Arium
        arium.compile()

        self._arium = arium
        return arium

    async def build_and_run(
        self,
        inputs: List[Union[str, ImageMessage]],
        variables: Optional[Dict[str, Any]] = None,
    ) -> List[dict]:
        """Build the Arium and run it with the given inputs and optional runtime variables."""
        arium = self.build()
        return await arium.run(inputs, variables=variables)

    def visualize(
        self, output_path: str = 'arium_graph.png', title: str = 'Arium Workflow'
    ) -> 'AriumBuilder':
        """Generate a visualization of the Arium graph."""
        if self._arium is None:
            self.build()

        self._arium.visualize_graph(output_path=output_path, graph_title=title)
        return self

    def reset(self) -> 'AriumBuilder':
        """Reset the builder to start fresh."""
        self._memory = None
        self._agents = []
        self._tools = []
        self._start_node = None
        self._end_nodes = []
        self._edges = []
        self._arium = None
        return self


# Convenience function for creating a builder
def create_arium() -> AriumBuilder:
    """Create a new AriumBuilder instance."""
    return AriumBuilder()
