from flo_ai.arium.base import BaseArium
from flo_ai.arium.memory import MessageMemory, BaseMemory
from flo_ai.llm.base_llm import ImageMessage
from typing import List
from flo_ai.models.agent import Agent
from flo_ai.tool.base_tool import Tool
from flo_ai.arium.models import StartNode, EndNode
from flo_ai.utils.logger import logger


class Arium(BaseArium):
    def __init__(self, memory: BaseMemory):
        super().__init__()
        self.is_compiled = False
        self.memory = memory if memory else MessageMemory()

    def compile(self):
        self.validate_graph()
        self.is_compiled = True

    async def run(self, inputs: List[str | ImageMessage]):
        if not self.is_compiled:
            raise ValueError('Arium is not compiled')

        if not self.memory:
            raise ValueError('Arium has no memory')

        if not self.nodes:
            raise ValueError('Arium has no nodes')

        return await self._execute_graph(inputs)

    async def _execute_graph(self, inputs: List[str | ImageMessage]):
        [self.memory.add(msg) for msg in inputs]

        current_node = self.nodes[self.start_node_name]
        current_edge = self.edges[self.start_node_name]

        logger.info(f'Executing graph from {current_node.name}')
        while current_node.name != self.end_node_name:
            # execute current node
            result = await self._execute_node(current_node)

            # update results to memory
            self._add_to_memory(result)

            # find next node post current node
            next_node_name = current_edge.router_fn(memory=self.memory)

            # find next edge
            # TODO: next_node_name might not be in self.edges if it's the end node. Handle this case
            next_edge = (
                self.edges[next_node_name] if next_node_name in self.edges else None
            )

            # update current node
            current_node = self.nodes[next_node_name]
            current_edge = next_edge

        return self.memory.get()

    async def _execute_node(self, node: Agent | Tool | StartNode | EndNode):
        if isinstance(node, Agent):
            return await node.run(self.memory.get())
        elif isinstance(node, Tool):
            return await node.execute(self.memory.get())
        elif isinstance(node, StartNode):
            return None
        elif isinstance(node, EndNode):
            return None

    def _add_to_memory(self, result: str):
        # TODO result will be None for start and end nodes
        if result:
            self.memory.add(result)
