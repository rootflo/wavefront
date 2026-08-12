from flo_ai.arium.base import BaseArium
from flo_ai.arium.memory import MessageMemory, MessageMemoryItem
from flo_ai.models import BaseMessage, UserMessage, TextMessageContent
from typing import List, Dict, Any, Optional, Callable
from flo_ai.agent.agent import Agent
from flo_ai.arium.base import AriumNodeType
from flo_ai.arium.models import StartNode, EndNode
from flo_ai.arium.events import AriumEventType, AriumEvent
from flo_ai.arium.nodes import AriumNode, ForEachNode, FunctionNode
from flo_ai.utils.logger import logger
from flo_ai.utils.variable_extractor import (
    extract_variables_from_inputs,
    extract_agent_variables,
    validate_multi_agent_variables,
    resolve_variables,
)
from flo_ai.telemetry.instrumentation import workflow_metrics
from flo_ai.telemetry import get_tracer
from flo_ai.utils.profiler import aprofile, record as _profile_record
from opentelemetry.trace import Status, StatusCode
import asyncio
import time


class Arium(BaseArium):
    def __init__(self, memory: MessageMemory):
        super().__init__()
        self.is_compiled = False
        self.memory = memory if memory else MessageMemory()
        # `memory` is the data bus nodes read from via input_filter, so it only
        # ever holds one (the final) result per node. `execution_trace` is a
        # strict superset — every message every node produced, including agent
        # tool calls/intermediate turns, every ForEach item, and every node of
        # a nested sub-workflow — for observability, never fed back into a
        # node's inputs. `_trace_memory` is the working buffer for the run in
        # progress; `execution_trace` is the finished snapshot exposed after
        # `run()` returns (mirrors how `self.memory` itself behaves).
        self.execution_trace: List[MessageMemoryItem] = []
        self._trace_memory: MessageMemory = MessageMemory()

    def compile(self):
        self.validate_graph()
        self.is_compiled = True

    async def run(
        self,
        inputs: List[BaseMessage] | str,
        variables: Optional[Dict[str, Any]] = None,
        event_callback: Optional[Callable[[AriumEvent], None]] = None,
        events_filter: Optional[List[AriumEventType]] = None,
        forwarded_from_parent: bool = False,
    ):
        """
        Execute the Arium workflow with optional event monitoring.

        Args:
            inputs: Input messages for the workflow
            variables: Variable substitutions for templated prompts
            event_callback: Function to call for each event (if None, no events are emitted)
            events_filter: List of event types to listen for (defaults to all)
            forwarded_from_parent: Set by AriumNode, not by callers. Marks these
                inputs as a parent workflow's node outputs being handed down, so
                their recorded producer is kept instead of being reset to
                'input'. A top-level caller's messages are always retagged.

        Returns:
            List of workflow execution results
        """
        variables = variables if variables is not None else {}
        if isinstance(inputs, str):
            inputs: list[BaseMessage] = [
                UserMessage(content=resolve_variables(inputs, variables))
            ]

        if not self.is_compiled:
            raise ValueError('Arium is not compiled')

        if not self.memory:
            raise ValueError('Arium has no memory')

        if not self.nodes:
            raise ValueError('Arium has no nodes')

        # Set default event filters to all event types if not specified
        if events_filter is None:
            events_filter = list(AriumEventType)

        # Emit workflow started event
        self._emit_event(AriumEventType.WORKFLOW_STARTED, event_callback, events_filter)

        # Get workflow name for telemetry
        workflow_name = getattr(self, 'name', 'unnamed_workflow')

        # Start telemetry tracing
        tracer = get_tracer()
        workflow_start_time = time.time()

        if tracer:
            with tracer.start_as_current_span(
                f'workflow.{workflow_name}',
                attributes={
                    'workflow.name': workflow_name,
                    'workflow.node_count': len(self.nodes),
                },
            ) as workflow_span:
                try:
                    # Extract and validate variables from inputs and all agents
                    self._extract_and_validate_variables(inputs, variables)

                    # Resolve variables in inputs and agent prompts
                    resolved_inputs = self._resolve_inputs(inputs, variables)
                    self._resolve_agent_prompts(variables)

                    # Execute the workflow with event support
                    result = await self._execute_graph(
                        resolved_inputs,
                        event_callback,
                        events_filter,
                        variables,
                        forwarded_from_parent,
                    )

                    # Record successful workflow execution
                    workflow_duration_ms = (time.time() - workflow_start_time) * 1000
                    workflow_metrics.record_workflow(workflow_name, 'success')
                    workflow_metrics.record_workflow_latency(
                        workflow_duration_ms, workflow_name
                    )

                    workflow_span.set_status(Status(StatusCode.OK))
                    workflow_span.set_attribute(
                        'workflow.result.length', len(str(result))
                    )

                    # Emit workflow completed event
                    self._emit_event(
                        AriumEventType.WORKFLOW_COMPLETED, event_callback, events_filter
                    )

                    self.execution_trace = self._trace_memory.get()
                    self._trace_memory = MessageMemory()
                    self.memory = MessageMemory()  # cleanup the graph

                    return result

                except Exception as e:
                    # Record failed workflow execution
                    workflow_duration_ms = (time.time() - workflow_start_time) * 1000
                    error_type = type(e).__name__

                    workflow_metrics.record_workflow(workflow_name, 'error')
                    workflow_metrics.record_error(workflow_name, error_type)
                    workflow_metrics.record_workflow_latency(
                        workflow_duration_ms, workflow_name
                    )

                    workflow_span.set_status(Status(StatusCode.ERROR, str(e)))
                    workflow_span.set_attribute('error.type', error_type)

                    # Emit workflow failed event
                    self._emit_event(
                        AriumEventType.WORKFLOW_FAILED,
                        event_callback,
                        events_filter,
                        error=str(e),
                    )
                    raise
        else:
            # No telemetry, execute without tracing
            try:
                # Extract and validate variables from inputs and all agents
                self._extract_and_validate_variables(inputs, variables)

                # Resolve variables in inputs and agent prompts
                resolved_inputs = self._resolve_inputs(inputs, variables)
                self._resolve_agent_prompts(variables)

                # Execute the workflow with event support
                result = await self._execute_graph(
                    resolved_inputs,
                    event_callback,
                    events_filter,
                    variables,
                    forwarded_from_parent,
                )

                # Emit workflow completed event
                self._emit_event(
                    AriumEventType.WORKFLOW_COMPLETED, event_callback, events_filter
                )

                self.execution_trace = self._trace_memory.get()
                self._trace_memory = MessageMemory()
                self.memory = MessageMemory()  # cleanup the graph

                return result

            except Exception as e:
                # Emit workflow failed event
                self._emit_event(
                    AriumEventType.WORKFLOW_FAILED,
                    event_callback,
                    events_filter,
                    error=str(e),
                )
                raise

    def _emit_event(
        self,
        event_type: AriumEventType,
        callback: Optional[Callable[[AriumEvent], None]],
        events_filter: Optional[List[AriumEventType]],
        **kwargs,
    ) -> None:
        """
        Emit an event if callback is provided and event type is in filtered list.

        Args:
            event_type: The type of event to emit
            callback: Function to call with the event (if None, no event is emitted)
            events_filter: List of event types to listen for
            **kwargs: Additional event data (node_name, error, etc.)
        """
        if callback and events_filter and event_type in events_filter:
            event = AriumEvent(event_type=event_type, timestamp=time.time(), **kwargs)
            callback(event)

    async def _execute_graph(
        self,
        inputs: List[BaseMessage],
        event_callback: Optional[Callable[[AriumEvent], None]] = None,
        events_filter: Optional[List[AriumEventType]] = None,
        variables: Optional[Dict[str, Any]] = None,
        forwarded_from_parent: bool = False,
    ):
        async with aprofile(
            f'arium.execute_graph[{getattr(self, "name", "unnamed_workflow")}]'
        ):
            return await self._execute_graph_impl(
                inputs, event_callback, events_filter, variables, forwarded_from_parent
            )

    async def _execute_graph_impl(
        self,
        inputs: List[BaseMessage],
        event_callback: Optional[Callable[[AriumEvent], None]] = None,
        events_filter: Optional[List[AriumEventType]] = None,
        variables: Optional[Dict[str, Any]] = None,
        forwarded_from_parent: bool = False,
    ):
        variables = variables if variables is not None else {}
        # A parent hands its nodes' outputs straight to a sub-workflow, so the
        # same BaseMessage objects land in this memory as 'input'. Retagging them
        # there would erase the producer the parent recorded, and an input_filter
        # reading provenance downstream would see 'input' for everything — hence
        # retag=False on that path only.
        #
        # Top-level inputs are always retagged. A caller can legitimately pass a
        # message that already carries a tag — feeding one workflow's results
        # into another, or reusing a message object — and that tag names a node
        # in a workflow that is not this one. Keeping it would let an unrelated
        # (or caller-chosen) name drive this workflow's routing and filtering.
        for msg in inputs:
            self.memory.add(
                MessageMemoryItem(
                    node='input',
                    occurrence=0,
                    result=msg,
                    retag=not forwarded_from_parent,
                )
            )
            # Same call again for the trace buffer: the message is already
            # tagged 'input' by the call above, so _tag()'s existing==node
            # check makes this a no-op copy-wise — safe to call twice.
            self._trace_memory.add(
                MessageMemoryItem(
                    node='input',
                    occurrence=0,
                    result=msg,
                    retag=not forwarded_from_parent,
                )
            )

        current_node = self.nodes[self.start_node_name]
        current_edge = self.edges[self.start_node_name]

        # Loop prevention: track execution steps and node visits
        max_iterations = 20  # Reasonable limit to prevent infinite loops
        iteration_count = 0
        node_visit_count = {}  # Track how many times each node is visited
        execution_path = []  # Track the path for debugging

        logger.info(f'Executing graph from {current_node.name}')
        while current_node.name not in self.end_node_names:
            # Check for iteration limit
            iteration_count += 1
            if iteration_count > max_iterations:
                logger.error(
                    f"Maximum iterations ({max_iterations}) exceeded. Execution path: {' -> '.join(execution_path)}"
                )
                raise RuntimeError(
                    f'Workflow exceeded maximum iterations ({max_iterations}). Possible infinite loop detected.'
                )

            # Track node visits
            node_visit_count[current_node.name] = (
                node_visit_count.get(current_node.name, 0) + 1
            )
            execution_path.append(current_node.name)

            # Check for excessive node visits (same node visited too many times)
            if node_visit_count[current_node.name] > 3:
                logger.error(
                    f"Node '{current_node.name}' visited {node_visit_count[current_node.name]} times. Execution path: {' -> '.join(execution_path)}"
                )
                raise RuntimeError(
                    f"Node '{current_node.name}' visited too many times ({node_visit_count[current_node.name]}). Possible infinite loop detected."
                )

            logger.info(
                f'Executing node: {current_node.name} (iteration {iteration_count})'
            )
            # execute current node
            result = await self._execute_node(
                current_node, event_callback, events_filter, variables
            )

            if isinstance(result, List):  # for each node will give results array
                # `current_node` is the node that just executed, so for a ForEach
                # this is the ForEach node itself and `current_node.name` is its
                # node name (e.g. "process_docs").
                if (
                    isinstance(current_node, ForEachNode)
                    and current_node.forward_all_results
                ):
                    # Forward every per-item result, each tagged with the ForEach
                    # node's name, so a downstream node can consume the whole
                    # collection via input_filter instead of only the last item.
                    foreach_node_name = current_node.name
                    for item_result in result:
                        if item_result is not None:
                            self._add_to_memory(
                                MessageMemoryItem(
                                    node=foreach_node_name, result=item_result
                                )
                            )
                else:
                    if result:
                        self._add_to_memory(
                            MessageMemoryItem(node=current_node.name, result=result[-1])
                        )
            else:
                # update results to memory
                if result:
                    self._add_to_memory(
                        MessageMemoryItem(node=current_node.name, result=result)
                    )

            # find next node post current node
            # Prepare execution context for router functions
            execution_context = {
                'node_visit_count': node_visit_count,
                'execution_path': execution_path,
                'iteration_count': iteration_count,
                'current_node': current_node.name,
            }

            # Handle both sync and async router functions
            # Try to call with execution context, fallback to memory only
            try:
                router_result = current_edge.router_fn(
                    memory=self.memory, execution_context=execution_context
                )
            except TypeError:
                # Router function doesn't accept execution_context parameter
                router_result = current_edge.router_fn(memory=self.memory)

            if asyncio.iscoroutine(router_result):
                next_node_name = await router_result
            else:
                next_node_name = router_result

            # Emit router decision event
            self._emit_event(
                AriumEventType.ROUTER_DECISION,
                event_callback,
                events_filter,
                node_name=current_node.name,
                router_choice=next_node_name,
            )

            # Emit edge traversed event
            self._emit_event(
                AriumEventType.EDGE_TRAVERSED,
                event_callback,
                events_filter,
                node_name=current_node.name,
            )

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
        self,
        inputs: List[BaseMessage],
        variables: Dict[str, Any],
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
        self,
        inputs: List[BaseMessage],
        variables: Optional[Dict[str, Any]] = None,
    ) -> List[BaseMessage]:
        """Resolve variables in input messages.

        Args:
            inputs: List of input messages
            variables: Dictionary of variable name to value mappings

        Returns:
            List of inputs with variables resolved
        """
        variables = variables if variables is not None else {}
        resolved_inputs = []
        for input_item in inputs:
            if isinstance(input_item, str):
                # Resolve variables in text input
                resolved_input = resolve_variables(input_item, variables)
                resolved_inputs.append(UserMessage(resolved_input))
            elif isinstance(input_item, TextMessageContent):
                resolved_inputs.append(
                    UserMessage(resolve_variables(input_item.text, variables))
                )
            else:
                # ImageMessageContent and DocumentMessage objects don't need variable resolution
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

    async def _execute_node(
        self,
        node: AriumNodeType,
        event_callback: Optional[Callable[[AriumEvent], None]] = None,
        events_filter: Optional[List[AriumEventType]] = None,
        variables: Optional[Dict[str, Any]] = None,
    ):
        """
        Execute a single node with optional event emission.

        Args:
            node: The node to execute
            event_callback: Function to call for events (if None, no events are emitted)
            events_filter: List of event types to listen for

        Returns:
            The result of node execution
        """
        variables = variables if variables is not None else {}
        # Determine node type for events
        if isinstance(node, Agent):
            node_type = 'agent'
        elif isinstance(node, FunctionNode):
            node_type = 'function'
        elif isinstance(node, ForEachNode):
            node_type = 'foreach'
        elif isinstance(node, AriumNode):
            node_type = 'arium'
        elif isinstance(node, StartNode):
            node_type = 'start'
        elif isinstance(node, EndNode):
            node_type = 'end'
        else:
            node_type = 'unknown'

        # Emit node started event
        self._emit_event(
            AriumEventType.NODE_STARTED,
            event_callback,
            events_filter,
            node_name=node.name,
            node_type=node_type,
        )

        start_time = time.time()
        workflow_name = getattr(self, 'name', 'unnamed_workflow')

        # Start node telemetry tracing
        tracer = get_tracer()
        memory_items = (
            self.memory.get(getattr(node, 'input_filter', None))
            if getattr(node, 'input_filter', None)
            else self.memory.get()
        )
        inputs = [item.result for item in memory_items]

        if tracer and node_type not in ['start', 'end']:
            with tracer.start_as_current_span(
                f'workflow.node.{node.name}',
                attributes={
                    'workflow.name': workflow_name,
                    'node.name': node.name,
                    'node.type': node_type,
                },
            ) as node_span:
                try:
                    result = await self._dispatch_node_run(
                        node, node_type, inputs, variables
                    )

                    # Calculate execution time
                    execution_time = time.time() - start_time
                    execution_time_ms = execution_time * 1000

                    # Record node metrics
                    workflow_metrics.record_node(
                        workflow_name, node.name, node_type, 'success'
                    )
                    workflow_metrics.record_node_latency(
                        execution_time_ms, workflow_name, node.name, node_type
                    )
                    _profile_record(f'node.{node.name}[{node_type}]', execution_time)

                    node_span.set_status(Status(StatusCode.OK))
                    node_span.set_attribute('node.execution_time_ms', execution_time_ms)

                    # Emit node completed event
                    self._emit_event(
                        AriumEventType.NODE_COMPLETED,
                        event_callback,
                        events_filter,
                        node_name=node.name,
                        node_type=node_type,
                        execution_time=execution_time,
                        node_output=self._serialize_node_output(result),
                    )

                    return result

                except Exception as e:
                    # Calculate execution time even on failure
                    execution_time = time.time() - start_time
                    execution_time_ms = execution_time * 1000
                    error_type = type(e).__name__

                    # Record node failure
                    workflow_metrics.record_node(
                        workflow_name, node.name, node_type, 'error'
                    )
                    workflow_metrics.record_node_latency(
                        execution_time_ms, workflow_name, node.name, node_type
                    )

                    node_span.set_status(Status(StatusCode.ERROR, str(e)))
                    node_span.set_attribute('error.type', error_type)
                    node_span.set_attribute('node.execution_time_ms', execution_time_ms)

                    # Emit node failed event
                    self._emit_event(
                        AriumEventType.NODE_FAILED,
                        event_callback,
                        events_filter,
                        node_name=node.name,
                        node_type=node_type,
                        execution_time=execution_time,
                        error=str(e),
                    )

                    # Re-raise the exception
                    raise e
        else:
            # No telemetry or start/end node, execute without tracing
            try:
                result = await self._dispatch_node_run(
                    node, node_type, inputs, variables
                )

                # Calculate execution time
                execution_time = time.time() - start_time
                _profile_record(f'node.{node.name}[{node_type}]', execution_time)

                # Emit node completed event
                self._emit_event(
                    AriumEventType.NODE_COMPLETED,
                    event_callback,
                    events_filter,
                    node_name=node.name,
                    node_type=node_type,
                    execution_time=execution_time,
                    node_output=self._serialize_node_output(result),
                )

                return result

            except Exception as e:
                # Calculate execution time even on failure
                execution_time = time.time() - start_time

                # Emit node failed event
                self._emit_event(
                    AriumEventType.NODE_FAILED,
                    event_callback,
                    events_filter,
                    node_name=node.name,
                    node_type=node_type,
                    execution_time=execution_time,
                    error=str(e),
                )

                # Re-raise the exception
                raise e

    async def _dispatch_node_run(
        self,
        node: AriumNodeType,
        node_type: str,
        inputs: List[BaseMessage],
        variables: Dict[str, Any],
    ):
        """Dispatch a node's ``run`` invocation under a profiler scope.

        Keeps the dispatch logic in one place so both the telemetry and
        non-telemetry branches of ``_execute_node`` get consistent profiling.
        """
        if node_type in ('start', 'end'):
            return None

        async with aprofile(f'node.{node.name}[{node_type}]'):
            if isinstance(node, Agent):
                # `conversation_history` is never reset between visits (a
                # workflow can legitimately loop back to the same agent node),
                # so only the messages this call adds — not the whole
                # history — belong to this node's trace entry. A plain
                # length-based slice isn't safe here: _setup_system_message
                # removes the old SystemMessage and re-appends a fresh one on
                # every run(), which shifts earlier messages' positions, so
                # the "new" messages are identified by object identity, not
                # by where they land in the list.
                ids_before = {id(m) for m in node.conversation_history}
                result = await node.run(inputs, variables={})
                for msg in node.conversation_history:
                    if id(msg) not in ids_before:
                        self._trace_memory.add(
                            MessageMemoryItem(node=node.name, result=msg)
                        )
                return result
            if isinstance(node, FunctionNode):
                # Agents get {} because their prompts were already resolved against
                # the variables in _resolve_agent_prompts. Function nodes have no
                # such earlier pass, so they need the real mapping here.
                result = await node.run(inputs, variables=variables)
                if result is not None:
                    self._trace_memory.add(
                        MessageMemoryItem(node=node.name, result=result)
                    )
                return result
            if isinstance(node, ForEachNode):
                foreach_results: List[MessageMemoryItem | BaseMessage] = await node.run(
                    inputs,
                    variables=variables,
                )
                for entry in node.last_execution_trace:
                    self._trace_memory.add(
                        MessageMemoryItem(
                            node=entry.node, result=entry.result, retag=False
                        )
                    )
                return self._flatten_results(foreach_results)
            if isinstance(node, AriumNode):
                arium_result: List[MessageMemoryItem] = await node.run(
                    inputs, variables=variables
                )
                # The nested Arium's own execution_trace is already fully
                # populated by the time its run() returns (recursion handles
                # arbitrarily deep nesting for free) — qualify each entry with
                # this wrapper's name so nested node names can't collide with
                # anything at this level.
                for entry in node.arium.execution_trace:
                    self._trace_memory.add(
                        MessageMemoryItem(
                            node=f'{node.name}.{entry.node}',
                            result=entry.result,
                            retag=False,
                        )
                    )
                return self._flatten_results(arium_result)
            return None

    def _flatten_results(
        self, sequence: List[MessageMemoryItem | BaseMessage | str]
    ) -> List[BaseMessage | str]:
        """
        Flatten a sequence of results by extracting .result from MessageMemoryItem instances.

        Args:
            sequence: List of items that may be MessageMemoryItem, BaseMessage, or str

        Returns:
            List of BaseMessage or str with MessageMemoryItem layers removed
        """
        return [
            item.result if isinstance(item, MessageMemoryItem) else item
            for item in sequence
        ]

    def _add_to_memory(self, message: MessageMemoryItem):
        """
        Store message in memory
        """
        self.memory.add(message)

    def _serialize_node_output(self, result: Any) -> Optional[str]:
        if result is None:
            return None
        if isinstance(result, str):
            return result
        if isinstance(result, list):
            # agent.run() returns conversation_history (all messages); take only
            # the last item, which is the agent's own reply for this node.
            if not result:
                return None
            return self._serialize_node_output(result[-1])
        if hasattr(result, 'content'):
            return self._serialize_node_output(result.content)
        if hasattr(result, 'text'):
            return result.text
        # DocumentMessageContent / ImageMessageContent — show url or type label
        media_type = getattr(result, 'type', None)
        if media_type in ('document', 'image'):
            url = getattr(result, 'url', None)
            mime = getattr(result, 'mime_type', None)
            if url:
                return f'[{media_type}: {url}]'
            return f'[{media_type}{f": {mime}" if mime else ""}]'
        return str(result)
