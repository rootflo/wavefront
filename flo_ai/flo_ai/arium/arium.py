from flo_ai.arium.base import BaseArium
from flo_ai.arium.memory import MessageMemory, BaseMemory
from flo_ai.llm.base_llm import ImageMessage
from typing import List, Dict, Any, Optional
from flo_ai.models.agent import Agent
from flo_ai.tool.base_tool import Tool
from flo_ai.arium.models import StartNode, EndNode
from flo_ai.utils.logger import logger
from flo_ai.utils.variable_extractor import (
    extract_variables_from_inputs,
    extract_agent_variables,
    validate_multi_agent_variables,
    resolve_variables,
)


class Arium(BaseArium):
    def __init__(self, memory: BaseMemory):
        super().__init__()
        self.is_compiled = False
        self.memory = memory if memory else MessageMemory()

    def compile(self):
        self.validate_graph()
        self.is_compiled = True

    async def run(
        self,
        inputs: List[str | ImageMessage],
        variables: Optional[Dict[str, Any]] = None,
    ):
        if not self.is_compiled:
            raise ValueError('Arium is not compiled')

        if not self.memory:
            raise ValueError('Arium has no memory')

        if not self.nodes:
            raise ValueError('Arium has no nodes')

        # Extract and validate variables from inputs and all agents
        self._extract_and_validate_variables(inputs, variables)

        # Resolve variables in inputs and agent prompts
        resolved_inputs = self._resolve_inputs(inputs, variables)
        self._resolve_agent_prompts(variables)

        return await self._execute_graph(resolved_inputs)

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

    def _extract_and_validate_variables(
        self, inputs: List[str | ImageMessage], variables: Dict[str, Any]
    ) -> None:
        """Extract variables from inputs and agents, then validate them.

        Args:
            inputs: List of input messages
            variables: Dictionary of variable name to value mappings

        Raises:
            ValueError: If any required variables are missing
        """
        # Extract variables from inputs
        input_variables = extract_variables_from_inputs(inputs)

        # Extract variables from all agents in the workflow
        agents_variables = {}
        for node in self.nodes.values():
            if isinstance(node, Agent):
                agent_vars = extract_agent_variables(node)
                if agent_vars:
                    agents_variables[node.name] = agent_vars

        # Validate input variables separately with cleaner error message
        if input_variables:
            missing_input_vars = input_variables - set(variables.keys())
            if missing_input_vars:
                provided_keys = sorted(variables.keys())
                raise ValueError(
                    f'Input contains missing variables: {sorted(missing_input_vars)}. '
                    f'Provided variables: {provided_keys}'
                )

        # Validate agent variables with detailed agent breakdown
        if agents_variables:
            validate_multi_agent_variables(agents_variables, variables)

    def _resolve_inputs(
        self, inputs: List[str | ImageMessage], variables: Dict[str, Any]
    ) -> List[str | ImageMessage]:
        """Resolve variables in input messages.

        Args:
            inputs: List of input messages
            variables: Dictionary of variable name to value mappings

        Returns:
            List of inputs with variables resolved
        """
        resolved_inputs = []
        for input_item in inputs:
            if isinstance(input_item, str):
                # Resolve variables in text input
                resolved_input = resolve_variables(input_item, variables)
                resolved_inputs.append(resolved_input)
            else:
                # ImageMessage objects don't need variable resolution
                resolved_inputs.append(input_item)
        return resolved_inputs

    def _resolve_agent_prompts(self, variables: Dict[str, Any]) -> None:
        """Resolve variables in all agent system prompts and mark them as resolved.

        Args:
            variables: Dictionary of variable name to value mappings
        """
        for node in self.nodes.values():
            if isinstance(node, Agent):
                node.system_prompt = resolve_variables(node.system_prompt, variables)
                node.resolved_variables = True

    async def _execute_node(self, node: Agent | Tool | StartNode | EndNode):
        if isinstance(node, Agent):
            # Variables are already resolved, pass empty dict to avoid re-processing
            return await node.run(self.memory.get(), variables={})
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
