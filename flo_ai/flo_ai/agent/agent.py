import inspect
import json
from typing import Dict, Any, List, Optional
from flo_ai.agent.base_agent import BaseAgent, AgentType, ReasoningPattern
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.llm.guarded_llm import GuardrailBlocked
from flo_ai.models.chat_message import (
    AssistantMessage,
    BaseMessage,
    MessageType,
    UserMessage,
    TextMessageContent,
    FunctionMessage,
    SystemMessage,
    ToolCall,
)
from flo_ai.agent.events import AgentEvent, AgentEventCallback, AgentEventType
from flo_ai.tool.base_tool import Tool, ToolExecutionError
from flo_ai.tool.plan_tool import PLAN_TOOL_NAME, Plan, create_plan_tool
from flo_ai.models.agent_error import AgentError
from flo_ai.utils.logger import logger
from flo_ai.utils.variable_extractor import (
    extract_variables_from_inputs,
    extract_agent_variables,
    validate_multi_agent_variables,
    resolve_variables,
)
from flo_ai.telemetry.instrumentation import (
    trace_agent_execution,
    agent_metrics,
)
from flo_ai.telemetry import get_tracer

# How many times in one run an agent is told to keep going after replying with
# text that is not a final answer, before that text is accepted as the answer.
MAX_CONTINUATION_NUDGES = 3


class Agent(BaseAgent):
    def __init__(
        self,
        name: str,
        system_prompt: str | AssistantMessage,
        llm: BaseLLM,
        tools: Optional[List[Tool]] = None,
        max_retries: int = 0,
        max_tool_calls: int = 5,
        reasoning_pattern: ReasoningPattern = ReasoningPattern.DIRECT,
        output_schema: Optional[Dict[str, Any]] = None,
        role: Optional[str] = None,
        act_as: Optional[str] = MessageType.ASSISTANT,
        input_filter: Optional[List[str]] = None,
    ):
        tools = list(tools or [])

        # A planning agent keeps its plan through a tool of its own, so it is
        # tool-using even when it was given no other tools.
        self.plan: Optional[Plan] = None
        if reasoning_pattern == ReasoningPattern.PLAN_EXECUTE:
            self.plan = Plan()
            tools.append(create_plan_tool(self.plan))

        # Determine agent type based on tools
        agent_type = AgentType.TOOL_USING if tools else AgentType.CONVERSATIONAL

        # Enhance system prompt with role if provided
        enhanced_prompt = system_prompt
        if role:
            if isinstance(system_prompt, str):
                enhanced_prompt = f'You are {role}. {system_prompt}'
            elif isinstance(system_prompt, AssistantMessage):
                enhanced_prompt = f'You are {role}. {system_prompt.content}'

        super().__init__(
            name=name,
            system_prompt=str(enhanced_prompt),
            agent_type=agent_type,
            llm=llm,
            max_retries=max_retries,
            max_tool_calls=max_tool_calls,
        )
        self.tools = tools
        self.tools_dict = {tool.name: tool for tool in self.tools}
        self.reasoning_pattern = reasoning_pattern
        self.output_schema = output_schema
        self.role = role
        self.act_as = act_as
        self.input_filter: Optional[List[str]] = input_filter
        self._on_event: Optional[AgentEventCallback] = None

    @trace_agent_execution()
    async def run(
        self,
        inputs: List[BaseMessage] | str,
        variables: Optional[Dict[str, Any]] = None,
        on_event: Optional[AgentEventCallback] = None,
    ) -> List[BaseMessage]:
        """Run one turn.

        Args:
            inputs: The new message(s), or a whole stored conversation to
                continue from, tool calls and results included.
            variables: Values for the placeholders in the prompt and inputs.
            on_event: Called, and awaited if it returns an awaitable, with an
                AgentEvent for each message the run adds to the conversation:
                tool calls, tool results, and the model's replies. It is for
                observing; an exception it raises is logged and the run goes on.
        """
        self._on_event = on_event
        try:
            return await self._run(inputs, variables)
        finally:
            self._on_event = None

    async def _record(
        self, message: BaseMessage, event_type: str, is_final: bool = False
    ) -> None:
        """Add a message this run produced to the history, and report it"""
        self.add_to_history(message)
        if self._on_event is None:
            return
        try:
            outcome = self._on_event(
                AgentEvent(
                    type=event_type,
                    agent=self.name,
                    message=message,
                    is_final=is_final,
                )
            )
            if inspect.isawaitable(outcome):
                await outcome
        except Exception:
            logger.exception(f'Agent {self.name}: on_event callback failed')

    async def _run(
        self,
        inputs: List[BaseMessage] | str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> List[BaseMessage]:
        variables = variables or {}
        if isinstance(inputs, str):
            inputs = [UserMessage(content=resolve_variables(inputs, variables))]

        # The conversation as it stood before this turn, so a turn the
        # guardrails refuse can be undone. Inputs are added to the history
        # below, before anything has looked at them — the check runs inside
        # ``llm.generate``, several frames down.
        #
        # A copy of the list rather than its length: _setup_system_message
        # rebuilds the history to strip old system messages, so by the time a
        # block is raised an index into the original no longer points at the
        # same message. Restoring the snapshot is exact regardless of what
        # reordered the list in between.
        history_before_turn = list(self.conversation_history)
        system_prompt_before_turn = self.system_prompt
        resolved_variables_before_turn = self.resolved_variables
        prompt_state_before_turn = (
            self._prompt_template,
            self._resolved_prompt,
            self._resolved_with,
        )

        # A plan covers one request; the next one starts with none.
        if self.plan is not None:
            self.plan.reset()

        # Perform runtime variable validation if not already resolved (single agent usage).
        # Variables passed on a later run are applied too, on top of the ones
        # already in use, so a reused agent picks up the new values. A workflow
        # resolves the prompt itself and passes none here.
        if not self.resolved_variables or variables:
            variables = {**self._resolved_with, **variables}
            self._resolved_with = variables

            # Extract variables from inputs and system prompt
            input_variables = extract_variables_from_inputs(inputs)
            agent_variables = extract_agent_variables(self)
            all_required_variables = input_variables.union(agent_variables)

            # Agents this one delegates to are only ever given a task, so
            # their prompts are filled in from this run's variables.
            delegates = self.all_delegate_agents()
            agents_variables = {
                delegate.name: extract_agent_variables(delegate)
                for delegate in delegates
            }
            agents_variables[self.name] = all_required_variables

            # Validate that all required variables are provided
            agents_variables = {
                name: needed for name, needed in agents_variables.items() if needed
            }
            if agents_variables:
                validate_multi_agent_variables(agents_variables, variables)

            # Resolve variables and mark as resolved
            self.resolve_system_prompt(variables)
            for delegate in delegates:
                delegate.resolve_system_prompt(variables)
                delegate.resolved_variables = True

            # Process inputs and resolve variables in string inputs
            for input in inputs:
                if isinstance(input, BaseMessage):
                    # checking whether the TextMessageContent is resolved
                    if isinstance(input.content, TextMessageContent) and variables:
                        input.content.text = resolve_variables(
                            input.content.text, variables
                        )
                    self.add_to_history(input)
                else:
                    raise ValueError(f'Invalid input type: {type(input)}')
            # after resolving agent system prompts and inputs, mark variables as resolved
            self.resolved_variables = True

        else:
            # Variables already resolved, process inputs without variable resolution
            for input in inputs:
                if isinstance(input, BaseMessage):
                    # Handle InputMessage - check content type
                    self.add_to_history(input)
                else:
                    raise ValueError(f'Invalid input type: {type(input)}')

        retry_count = 0

        try:
            # If no tools, act as conversational agent
            if not self.tools:
                return await self._run_conversational(retry_count, variables)

            # Otherwise, run as tool agent
            return await self._run_with_tools(retry_count, variables)
        except GuardrailBlocked:
            # A refused turn leaves no trace. The payload never reached the
            # provider, so nothing about it is part of the conversation — and
            # keeping it would poison every turn after it, since the history is
            # re-scanned on each one and the refused message would still be
            # sitting in it.
            #
            # The whole turn goes, not just the offending message: a block mid
            # tool-loop leaves an assistant turn whose tool calls were never
            # answered, which providers reject on the next request. There is no
            # assistant reply to keep either way, because this path raises.
            #
            # The system prompt is re-added by _setup_system_message on the next
            # run, which strips any existing one first, so restoring a snapshot
            # taken before it moved is safe.
            self.conversation_history = history_before_turn
            self.system_prompt = system_prompt_before_turn
            self.resolved_variables = resolved_variables_before_turn
            (
                self._prompt_template,
                self._resolved_prompt,
                self._resolved_with,
            ) = prompt_state_before_turn
            raise

    async def _handle_response_with_parser(
        self, assistant_message: Optional[str], role: str, response: Dict[str, Any]
    ) -> None:
        if assistant_message:
            reply = AssistantMessage(role=role, content=assistant_message)
        else:
            possible_tool_message = await self.llm.get_function_call(response)
            if possible_tool_message:
                reply = AssistantMessage(
                    role=role, content=str(possible_tool_message['arguments'])
                )
            else:
                logger.debug('Warning: No message content found in response')
                reply = AssistantMessage(
                    role=role,
                    content='No message content found in response',
                )
        await self._record(reply, AgentEventType.MESSAGE, is_final=True)

    async def _run_conversational(
        self, retry_count: int, variables: Optional[Dict[str, Any]] = None
    ) -> List[BaseMessage]:
        """Run as a conversational agent when no tools are provided"""
        variables = variables or {}

        # Create and add system message once before the retry loop
        self._setup_system_message(variables, include_react=False)

        while retry_count <= self.max_retries:
            try:
                messages = await self._get_message_history(variables)

                logger.debug(f'Sending messages to LLM: {messages}')
                response = await self.llm.generate(
                    messages, output_schema=self.output_schema
                )
                logger.debug(f'Raw LLM Response: {response}')

                assistant_message = self.llm.get_message_content(response)
                logger.debug(f'Extracted message: {assistant_message}')

                # Ensure act_as is not None (default to 'assistant' if missing)
                role = self.act_as if self.act_as is not None else MessageType.ASSISTANT

                await self._handle_response_with_parser(
                    assistant_message, role, response
                )

                return self.conversation_history

            except GuardrailBlocked:
                raise
            except Exception as e:
                retry_count += 1
                # The error is analysed on its own: the conversation is not
                # needed to judge it, and sending it would repeat every message
                # in a second request.
                context = {'attempt': retry_count}

                should_retry, analysis = await self.handle_error(e, context)

                if should_retry and retry_count <= self.max_retries:
                    await self._record(
                        AssistantMessage(
                            content=f'Error occurred. Analysis: {analysis}'
                        ),
                        AgentEventType.NOTICE,
                    )
                    continue
                else:
                    raise AgentError(
                        f'Failed after {retry_count} attempts. Last error: {analysis}',
                        original_error=e,
                    )

        # return conversation history if we exit the loop without returning
        return self.conversation_history

    async def _run_with_tools(
        self, retry_count: int = 0, variables: Optional[Dict[str, Any]] = None
    ) -> List[BaseMessage]:
        """Run as a tool-using agent when tools are provided"""
        variables = variables or {}
        logger.debug('Running agent with tools')

        # Create and add system message once before the retry loop
        self._setup_system_message(variables, include_react=True)

        while retry_count <= self.max_retries:
            try:
                messages = await self._get_message_history(variables)

                # Keep executing tools until we get a final answer
                tool_call_count = 0
                # Plan bookkeeping is counted apart from real work, so keeping
                # the plan current does not eat into max_tool_calls. It still
                # needs a ceiling of its own.
                plan_update_count = 0
                max_plan_updates = 2 * self.max_tool_calls + 2
                nudge_count = 0
                function_response = None
                response = None
                while (
                    tool_call_count < self.max_tool_calls
                    and plan_update_count < max_plan_updates
                ):
                    formatted_tools = self.llm.format_tools_for_llm(self.tools)
                    response = await self.llm.generate(
                        messages,
                        functions=formatted_tools,
                        output_schema=self.output_schema,
                    )

                    # Handle ReACT and CoT patterns
                    function_call = await self.llm.get_function_call(response)

                    # If no function call, check if this is truly a final answer
                    if not function_call:
                        assistant_message = self.llm.get_message_content(response)
                        if assistant_message:
                            # Check if this is a final answer or just intermediate reasoning
                            if self.plan is not None:
                                # The plan says whether there is work left, so
                                # no classifier call is needed.
                                is_final = not self.plan.unfinished()
                            else:
                                is_final = await self._is_final_answer(
                                    assistant_message, tool_call_count, messages
                                )
                            if not is_final and nudge_count >= MAX_CONTINUATION_NUDGES:
                                logger.warning(
                                    f'Agent {self.name} was asked to continue '
                                    f'{nudge_count} times without calling a tool; '
                                    'accepting its reply as the final answer.'
                                )
                                is_final = True
                            if is_final:
                                # Ensure act_as is not None (default to 'assistant' if missing)
                                role = (
                                    self.act_as
                                    if self.act_as is not None
                                    else MessageType.ASSISTANT
                                )
                                await self._record(
                                    AssistantMessage(
                                        role=role,
                                        content=self._strip_final_answer_token(
                                            assistant_message
                                        ),
                                    ),
                                    AgentEventType.MESSAGE,
                                    is_final=True,
                                )
                                return self.conversation_history
                            else:
                                # This is intermediate reasoning, add to context and continue
                                msg_preview = (
                                    assistant_message[:100]
                                    if len(assistant_message) > 100
                                    else assistant_message
                                )
                                logger.debug(
                                    f'Detected intermediate reasoning (not final answer): {msg_preview}...'
                                )
                                # Ensure act_as is not None (default to 'assistant' if missing)
                                role = (
                                    self.act_as
                                    if self.act_as is not None
                                    else MessageType.ASSISTANT
                                )
                                await self._record(
                                    AssistantMessage(
                                        role=role, content=assistant_message
                                    ),
                                    AgentEventType.MESSAGE,
                                )
                                nudge = self._continuation_nudge()
                                await self._record(
                                    UserMessage(content=nudge), AgentEventType.NOTICE
                                )
                                # The request being built has to carry both as
                                # well, or the model is sent the same prompt
                                # again and gives the same reply.
                                messages.append(
                                    {'role': role, 'content': assistant_message}
                                )
                                messages.append(
                                    {'role': MessageType.USER, 'content': nudge}
                                )
                                nudge_count += 1
                                continue
                        break

                    # The call is part of the conversation in its own right:
                    # recorded before the tool runs, with its arguments, so a
                    # later turn (or a session replayed from storage) sees what
                    # was asked for and not only what came back.
                    role = (
                        self.act_as
                        if self.act_as is not None
                        else MessageType.ASSISTANT
                    )
                    function_name = function_call.get('name') or 'unknown'
                    # Get tool_use_id if available (LLM-specific, e.g., Claude)
                    tool_use_id = self.llm.get_tool_use_id(function_call)
                    raw_arguments = function_call.get('arguments')
                    arguments_error: Optional[Exception] = None
                    try:
                        function_args = (
                            json.loads(raw_arguments)
                            if isinstance(raw_arguments, str)
                            else raw_arguments
                        ) or {}
                    except json.JSONDecodeError as e:
                        # Still recorded, so the error below answers a call.
                        function_args = {}
                        arguments_error = e

                    call_text = self.llm.get_message_content(response) or ''
                    tool_calls = [
                        ToolCall(
                            name=function_name, arguments=function_args, id=tool_use_id
                        )
                    ]
                    await self._record(
                        AssistantMessage(
                            role=role, content=call_text, tool_calls=tool_calls
                        ),
                        AgentEventType.TOOL_CALL,
                    )

                    # The same call, in the request being built. A provider
                    # that hands back its own form of the message (Claude's
                    # raw_content) gets that; otherwise it is formatted from
                    # the record.
                    assistant_message_content = (
                        self.llm.get_assistant_message_for_tool_call(response)
                    )
                    if assistant_message_content:
                        messages.append(
                            {
                                'role': self.act_as,
                                'content': assistant_message_content,
                            }
                        )
                    else:
                        call_message = self.llm.format_tool_call_message(
                            call_text, tool_calls
                        )
                        if call_message is not None:
                            messages.append(call_message)

                    # Execute the tool
                    try:
                        if arguments_error is not None:
                            raise arguments_error

                        tool = self.tools_dict[function_name]

                        # Track tool execution with telemetry
                        tracer = get_tracer()

                        if tracer:
                            with tracer.start_as_current_span(
                                f'agent.tool.{function_name}',
                                attributes={
                                    'tool.name': function_name,
                                    'agent.name': self.name,
                                },
                            ) as tool_span:
                                function_response = await tool.run(
                                    inputs=[], variables=None, **function_args
                                )
                                tool_span.set_attribute(
                                    'tool.result.length', len(str(function_response))
                                )
                        else:
                            function_response = await tool.run(
                                inputs=[], variables=None, **function_args
                            )

                        agent_metrics.record_tool_call(
                            self.name, function_name, 'success'
                        )

                        if self.plan is not None and function_name == PLAN_TOOL_NAME:
                            plan_update_count += 1
                        else:
                            tool_call_count += 1

                        # Add function call result to history using OpenAI's "function" role format
                        # According to OpenAI API: {"role": "function", "name": "<function-name>", "content": "<result>"}
                        await self._record(
                            FunctionMessage(
                                content=str(
                                    'Here is the result of the tool call: \n'
                                    + str(function_response)
                                ),
                                name=function_name,
                                tool_call_id=tool_use_id,
                            ),
                            AgentEventType.TOOL_RESULT,
                        )

                        # Add the function response to messages for context
                        # LLM-specific implementations format the message appropriately
                        function_result_msg = self.llm.format_function_result_message(
                            function_name, str(function_response), tool_use_id
                        )
                        messages.append(function_result_msg)

                    except (json.JSONDecodeError, KeyError, ToolExecutionError) as e:
                        # Record tool call failure
                        agent_metrics.record_tool_call(
                            self.name, function_name, 'error'
                        )

                        retry_count += 1
                        context = {
                            'function_call': function_call,
                            'attempt': retry_count,
                        }
                        should_retry, analysis = await self.handle_error(e, context)

                        # Recorded as the result of the call either way. The
                        # model needs to see what went wrong to correct it, and
                        # a call left unanswered in the history would make the
                        # provider reject every later request.
                        error_text = f'Tool execution error: {analysis}'
                        await self._record(
                            FunctionMessage(
                                content=error_text,
                                name=function_name,
                                tool_call_id=tool_use_id,
                            ),
                            AgentEventType.TOOL_RESULT,
                        )

                        if should_retry and retry_count <= self.max_retries:
                            # Record retry
                            agent_metrics.record_retry(
                                self.name, 'tool_execution_error'
                            )
                            messages.append(
                                self.llm.format_function_result_message(
                                    function_name, error_text, tool_use_id
                                )
                            )
                            continue
                        raise AgentError(
                            f'Tool execution failed: {analysis}', original_error=e
                        )

                # The model returned neither text nor a tool call. Record that
                # as its reply, so the run does not end on someone else's
                # message (a workflow takes the last one as this agent's output).
                if (
                    tool_call_count == 0
                    and plan_update_count == 0
                    and response is not None
                ):
                    role = (
                        self.act_as
                        if self.act_as is not None
                        else MessageType.ASSISTANT
                    )
                    await self._handle_response_with_parser(None, role, response)
                    return self.conversation_history

                # Generate final response if we've hit the tool call limit or exited the loop
                system_message = SystemMessage(
                    content='Please provide a final answer based on all the tool results above.'
                )
                self.add_to_history(system_message)
                messages = await self._get_message_history(variables)

                final_response = await self.llm.generate(
                    messages,
                    output_schema=self.output_schema,
                )

                assistant_message = self.llm.get_message_content(final_response)
                role = self.act_as if self.act_as is not None else MessageType.ASSISTANT
                await self._handle_response_with_parser(
                    assistant_message, role, final_response
                )

                return self.conversation_history

            except GuardrailBlocked:
                raise
            except Exception as e:
                retry_count += 1
                # The error is analysed on its own: the conversation is not
                # needed to judge it, and sending it would repeat every message
                # in a second request.
                context = {'attempt': retry_count}

                should_retry, analysis = await self.handle_error(e, context)
                if should_retry and retry_count <= self.max_retries:
                    # Record retry
                    agent_metrics.record_retry(self.name, 'execution_error')

                    await self._record(
                        AssistantMessage(
                            content=f'Error occurred. Analysis: {analysis}'
                        ),
                        AgentEventType.NOTICE,
                    )
                    continue

                raise AgentError(
                    f'Failed after {retry_count} attempts. Last error: {analysis}',
                    original_error=e,
                )

        raise AgentError(f'Failed after maximum {self.max_retries} attempts.')

    def _setup_system_message(
        self, variables: Optional[Dict[str, Any]] = None, include_react: bool = False
    ) -> None:
        """
        Create and add system message once before retry loop.
        Removes any existing system messages to avoid duplicates on retries.

        Args:
            variables: Optional variables for resolving system prompt
            include_react: Whether to check for REACT reasoning pattern (only for tool-using agents)
        """
        variables = variables or {}

        # Remove any existing system messages to avoid duplicates on retries
        self.conversation_history = [
            msg
            for msg in self.conversation_history
            if not isinstance(msg, SystemMessage)
        ]

        # Resolve variables in system prompt based on reasoning pattern
        if include_react and self.reasoning_pattern == ReasoningPattern.REACT:
            system_content = self._get_react_prompt(variables)
        elif self.reasoning_pattern == ReasoningPattern.COT:
            system_content = self._get_cot_prompt(variables)
        elif self.reasoning_pattern == ReasoningPattern.PLAN_EXECUTE:
            system_content = self._get_plan_execute_prompt(variables)
        else:
            system_content = resolve_variables(self.system_prompt, variables)

        # First, ahead of the inputs already in the history: providers expect
        # the system message to open the conversation.
        self.conversation_history.insert(0, SystemMessage(content=system_content))

    def _get_react_prompt(self, variables: Optional[Dict[str, Any]] = None) -> str:
        """Get system prompt modified for ReACT pattern"""
        variables = variables or {}

        tools_desc = '\n'.join(
            [f'- {tool.name}: {tool.description}' for tool in self.tools]
        )

        # Resolve variables in the base system prompt
        resolved_system_prompt = resolve_variables(self.system_prompt, variables)

        react_prompt = f"""{resolved_system_prompt}
            When solving tasks, follow this format:

            Thought: Analyze the situation and think about what to do
            Action: Use available tools in the format: tool_name(param1: "value1", param2: "value2")
            Observation: The result of the action
            ... (repeat Thought/Action/Observation if needed)
            Final Answer: [Your complete answer to the user's question]

            Available tools:
            {tools_desc}

            Remember to:
            1. Think carefully about what needs to be done
            2. Use tools when needed
            3. Make observations about tool results
            4. Conclude with a final answer when the task is complete

            IMPORTANT: When you have enough information to answer the user's question, you MUST prefix your response with "Final Answer:" to indicate completion."""

        return react_prompt

    def _get_cot_prompt(self, variables: Optional[Dict[str, Any]] = None) -> str:
        """Get system prompt modified for Chain of Thought pattern"""
        variables = variables or {}

        tools_desc = '\n'.join(
            [f'- {tool.name}: {tool.description}' for tool in self.tools]
        )

        # Resolve variables in the base system prompt
        resolved_system_prompt = resolve_variables(self.system_prompt, variables)

        cot_prompt = f"""{resolved_system_prompt}
            When solving tasks, follow this Chain of Thought reasoning format:

            Let me think through this step by step:
            1. First, I need to understand what is being asked...
            2. Then, I should consider what information or tools I need.... Use available tools in the format: tool_name(param1: "value1", param2: "value2")
            3. Next, I'll analyze the available options...
            4. Finally, I'll provide a well-reasoned answer...

            Available tools:
            {tools_desc}

            Remember to:
            1. Break down complex problems into smaller steps
            2. Think through each step logically
            3. Use tools when needed to gather information
            4. Provide clear reasoning for your conclusions
            5. End with a final, well-justified answer

            IMPORTANT: When you have gathered all necessary information and are ready to provide your complete answer, you MUST prefix your response with "Final Answer:" to indicate completion."""

        return cot_prompt

    def _get_plan_execute_prompt(
        self, variables: Optional[Dict[str, Any]] = None
    ) -> str:
        """Get system prompt modified for the plan-and-execute pattern"""
        variables = variables or {}

        # Resolve variables in the base system prompt
        resolved_system_prompt = resolve_variables(self.system_prompt, variables)

        return f"""{resolved_system_prompt}

You work by planning first and then carrying the plan out. The {PLAN_TOOL_NAME} tool holds your plan.

1. If the request needs more than one step, start by calling {PLAN_TOOL_NAME} with every step, each "pending".
2. Carry out the steps in order with your other tools. When a step is done, call {PLAN_TOOL_NAME} with the full list again, marking that step "completed" and the next one "in_progress".
3. Change the plan when you learn something that changes it: add steps, or mark steps you no longer need as "skipped".
4. Give your final answer only when every step is "completed" or "skipped".

If the request can be answered directly, answer it without making a plan."""

    def _strip_final_answer_token(self, message: str) -> str:
        """Drop the "Final Answer:" marker the ReACT and CoT prompts ask for"""
        if self.reasoning_pattern not in (ReasoningPattern.REACT, ReasoningPattern.COT):
            return message
        _, token, answer = message.partition('Final Answer:')
        if not token:
            index = message.lower().find('final answer:')
            answer = message[index + len('final answer:') :] if index >= 0 else ''
        return answer.strip() or message

    def delegate_agents(self) -> List['Agent']:
        """The agents this one can hand work to through its tools"""
        found: List['Agent'] = []
        for tool in self.tools:
            # A tool given a custom name or description is wrapped; the agents
            # are on the tool underneath.
            base_tool = getattr(tool, 'base_tool', tool)
            for agent in getattr(base_tool, 'agents', []):
                if agent not in found:
                    found.append(agent)
        return found

    def all_delegate_agents(self) -> List['Agent']:
        """Every agent reachable through tools, at any depth"""
        found: List['Agent'] = []
        pending = self.delegate_agents()
        while pending:
            agent = pending.pop()
            if agent is self or agent in found:
                continue
            found.append(agent)
            pending.extend(agent.delegate_agents())
        return found

    def add_tool(self, tool: Tool) -> None:
        """Give the agent another tool"""
        self.tools.append(tool)
        self.tools_dict[tool.name] = tool

    def _continuation_nudge(self) -> str:
        """What to tell the model after a reply that is not a final answer"""
        if self.plan is not None:
            return (
                'Your plan still has unfinished steps:\n'
                f'{self.plan.render()}\n'
                f'Continue with the next step, or call {PLAN_TOOL_NAME} to mark '
                'steps completed or skipped if the plan has changed.'
            )
        return 'Based on your reasoning, please proceed with the necessary tool calls to complete the task.'

    def as_tool(
        self, description: Optional[str] = None, name: Optional[str] = None
    ) -> Tool:
        """Expose this agent as a tool another agent can delegate to"""
        from flo_ai.tool.agent_tool import agent_as_tool

        return agent_as_tool(self, description=description, name=name)

    async def _is_final_answer(
        self, message: str, tool_call_count: int, messages: List[Dict[str, Any]]
    ) -> bool:
        """
        Determine if a message is a final answer or intermediate reasoning.
        Uses structured token detection (like LangChain's ReAct) with LLM fallback.

        Approach inspired by LangChain/CrewAI:
        1. Primary: Check for explicit "Final Answer:" token
        2. Fallback: Use LLM-based classification for robustness
        """
        message_stripped = message.strip()
        message_lower = message_stripped.lower()

        # Primary Detection: Explicit "Final Answer:" token (ReAct pattern)
        # This is the most reliable method used by LangChain and similar frameworks
        if message_stripped.startswith('Final Answer:') or message_lower.startswith(
            'final answer:'
        ):
            logger.debug('Explicit "Final Answer:" token detected - this is final')
            return True

        # Check if "Final Answer:" appears anywhere in the response
        # (agent might add context before the token)
        if 'final answer:' in message_lower:
            logger.debug('"Final Answer:" token found in response - treating as final')
            return True

        # Secondary Detection: Use LLM-based analysis for cases without explicit tokens
        # This handles:
        # - Agents not following the format perfectly
        # - Direct mode (without ReAct/CoT patterns)
        # - Edge cases where the agent provides answer without token

        analysis_prompt = f"""You are a classifier that determines if an AI agent's response is a FINAL ANSWER or INTERMEDIATE REASONING.

Agent's Response:
"{message_stripped}"

Context:
- Tool calls executed so far: {tool_call_count}
- Total conversation turns: {len(messages)}

Classification Criteria:

FINAL ANSWER - The response is final if it:
✓ Directly answers the user's original question with concrete information
✓ Provides specific data, results, or conclusions
✓ Does not suggest or request additional actions
✓ Reads like a complete, standalone answer
✓ Contains synthesis of information already gathered

INTERMEDIATE REASONING - The response is intermediate if it:
✗ Describes plans or intentions for what to do next
✗ Expresses need to gather more information
✗ Contains thinking/reasoning WITHOUT providing the actual answer
✗ Poses questions or expresses uncertainty about next steps
✗ Mentions specific tools it wants to use

Examples of INTERMEDIATE:
- "I need to query the database schema first"
- "Let me check the table structure"
- "First, I should examine..."

Examples of FINAL:
- "Based on the query results, the table contains 1,245 records..."
- "The analysis shows that revenue increased by 23%..."
- "After examining the data, the answer is..."

Respond with EXACTLY one word: "FINAL" or "INTERMEDIATE"
"""

        try:
            analysis_messages = [
                {
                    'role': MessageType.SYSTEM,
                    'content': 'You are a precise classification system. Respond with only FINAL or INTERMEDIATE.',
                },
                {'role': MessageType.USER, 'content': analysis_prompt},
            ]
            analysis_response = await self.llm.generate(analysis_messages)
            analysis = self.llm.get_message_content(analysis_response).strip().upper()

            is_final = (
                'FINAL' in analysis
                and 'INTERMEDIATE' not in analysis
                and 'NOT FINAL' not in analysis
            )
            msg_preview = (
                message_stripped[:80]
                if len(message_stripped) > 80
                else message_stripped
            )
            logger.debug(
                f'LLM classifier: "{analysis}" -> is_final={is_final} (message preview: "{msg_preview}...")'
            )
            return is_final

        except Exception as e:
            logger.warning(
                f'LLM classification failed: {e}. Defaulting to final=False to allow continuation.'
            )
            # Conservative default: treat as intermediate to avoid premature exit
            # This is safer as it allows the agent to continue rather than stopping too early
            return False
