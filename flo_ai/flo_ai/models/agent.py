import json
from typing import Dict, Any, List, Optional
from flo_ai.models.base_agent import BaseAgent, AgentType, ReasoningPattern
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.models.chat_message import (
    AssistantMessage,
    BaseMessage,
    MessageType,
    UserMessage,
    TextMessageContent,
    FunctionMessage,
)
from flo_ai.tool.base_tool import Tool, ToolExecutionError
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
            system_prompt=enhanced_prompt,
            agent_type=agent_type,
            llm=llm,
            max_retries=max_retries,
            max_tool_calls=max_tool_calls,
        )
        self.tools = tools or []
        self.tools_dict = {tool.name: tool for tool in self.tools}
        self.reasoning_pattern = reasoning_pattern
        self.output_schema = output_schema
        self.role = role
        self.act_as = act_as
        self.input_filter: Optional[List[str]] = input_filter

    @trace_agent_execution()
    async def run(
        self,
        inputs: List[BaseMessage] | str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> str:
        variables = variables or {}
        if isinstance(inputs, str):
            inputs = [UserMessage(TextMessageContent(text=inputs))]

        # Perform runtime variable validation if not already resolved (single agent usage)
        if not self.resolved_variables:
            # Extract variables from inputs and system prompt
            input_variables = extract_variables_from_inputs(inputs)
            agent_variables = extract_agent_variables(self)
            all_required_variables = input_variables.union(agent_variables)

            # Validate that all required variables are provided
            if all_required_variables:
                agents_variables = {self.name: all_required_variables}
                validate_multi_agent_variables(agents_variables, variables)

            # Resolve variables and mark as resolved
            self.system_prompt = resolve_variables(self.system_prompt, variables)

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

        # If no tools, act as conversational agent
        if not self.tools:
            return await self._run_conversational(retry_count, variables)

        # Otherwise, run as tool agent
        return await self._run_with_tools(retry_count, variables)

    async def _run_conversational(
        self, retry_count: int, variables: Optional[Dict[str, Any]] = None
    ) -> str:
        """Run as a conversational agent when no tools are provided"""
        variables = variables or {}

        while retry_count <= self.max_retries:
            try:
                # Resolve variables in system prompt
                system_content = (
                    self._get_cot_prompt(variables)
                    if self.reasoning_pattern == ReasoningPattern.COT
                    else resolve_variables(self.system_prompt, variables)
                )
                system_message = AssistantMessage(
                    role=MessageType.SYSTEM,
                    content=TextMessageContent(text=system_content),
                )
                self.add_to_history(system_message)
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

                if assistant_message:
                    self.add_to_history(
                        AssistantMessage(role=role, content=assistant_message)
                    )
                else:
                    possible_tool_message = await self.llm.get_function_call(response)
                    if possible_tool_message:
                        self.add_to_history(
                            AssistantMessage(
                                role=role, content=possible_tool_message['arguments']
                            )
                        )
                    else:
                        logger.debug('Warning: No message content found in response')
                        self.add_to_history(
                            AssistantMessage(
                                role=role,
                                content='No message content found in response',
                            )
                        )

                return self.conversation_history

            except Exception as e:
                retry_count += 1
                context = {
                    'conversation_history': self.conversation_history,
                    'attempt': retry_count,
                }

                should_retry, analysis = await self.handle_error(e, context)

                if should_retry and retry_count <= self.max_retries:
                    self.add_to_history(
                        AssistantMessage(
                            content=f'Error occurred. Analysis: {analysis}'
                        )
                    )
                    continue
                else:
                    raise AgentError(
                        f'Failed after {retry_count} attempts. Last error: {analysis}',
                        original_error=e,
                    )

    async def _run_with_tools(
        self, retry_count: int = 0, variables: Optional[Dict[str, Any]] = None
    ) -> str:
        """Run as a tool-using agent when tools are provided"""
        variables = variables or {}
        print('running with tools')

        while retry_count <= self.max_retries:
            try:
                # Resolve variables in system prompt based on reasoning pattern
                if self.reasoning_pattern == ReasoningPattern.REACT:
                    system_content = self._get_react_prompt(variables)
                elif self.reasoning_pattern == ReasoningPattern.COT:
                    system_content = self._get_cot_prompt(variables)
                else:
                    system_content = resolve_variables(self.system_prompt, variables)

                system_message = AssistantMessage(
                    role=MessageType.SYSTEM, content=system_content
                )
                self.add_to_history(system_message)
                messages = await self._get_message_history(variables)

                # Keep executing tools until we get a final answer
                tool_call_count = 0
                while tool_call_count < self.max_tool_calls:
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
                            is_final = await self._is_final_answer(
                                assistant_message, tool_call_count, messages
                            )
                            if is_final:
                                # Ensure act_as is not None (default to 'assistant' if missing)
                                role = (
                                    self.act_as
                                    if self.act_as is not None
                                    else MessageType.ASSISTANT
                                )
                                self.add_to_history(
                                    AssistantMessage(
                                        role=role, content=assistant_message
                                    )
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
                                self.add_to_history(
                                    AssistantMessage(
                                        role=role, content=assistant_message
                                    )
                                )
                                self.add_to_history(
                                    UserMessage(
                                        content='Based on your reasoning, please proceed with the necessary tool calls to complete the task.',
                                    )
                                )
                                continue
                        break

                    # If there's a function call, add the assistant's response
                    # LLM-specific implementations handle special formatting (e.g., Claude's raw_content)
                    assistant_message_content = (
                        self.llm.get_assistant_message_for_tool_call(response)
                    )
                    if assistant_message_content:
                        # LLM returned special formatting (e.g., Claude's raw_content)
                        messages.append(
                            {
                                'role': self.act_as,
                                'content': assistant_message_content,
                            }
                        )
                    else:
                        # Use default text content extraction
                        assistant_text = self.llm.get_message_content(response)
                        if assistant_text:
                            messages.append(
                                {
                                    'role': self.act_as,
                                    'content': assistant_text,
                                }
                            )

                    # Execute the tool
                    try:
                        function_name = function_call['name']
                        # Get tool_use_id if available (LLM-specific, e.g., Claude)
                        tool_use_id = self.llm.get_tool_use_id(function_call)
                        if isinstance(function_call['arguments'], str):
                            function_args = json.loads(function_call['arguments'])
                        else:
                            function_args = function_call['arguments']

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

                        tool_call_count += 1

                        # Add function call result to history using OpenAI's "function" role format
                        # According to OpenAI API: {"role": "function", "name": "<function-name>", "content": "<result>"}
                        self.add_to_history(
                            FunctionMessage(
                                content=str(
                                    'Here is the result of the tool call: \n'
                                    + str(function_response)
                                ),
                                name=function_name,
                            )
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
                        if should_retry and retry_count <= self.max_retries:
                            # Record retry
                            agent_metrics.record_retry(
                                self.name, 'tool_execution_error'
                            )

                            self.add_to_history(
                                AssistantMessage(
                                    content=f'Tool execution error: {analysis}'
                                )
                            )
                            continue
                        raise AgentError(
                            f'Tool execution failed: {analysis}', original_error=e
                        )

                # Generate final response if we've hit the tool call limit or exited the loop
                system_message = AssistantMessage(
                    role=MessageType.SYSTEM,
                    content=TextMessageContent(
                        text='Please provide a final answer based on all the tool results above.'
                    ),
                )
                self.add_to_history(system_message)
                messages = await self._get_message_history(variables)

                final_response = await self.llm.generate(
                    messages,
                    output_schema=self.output_schema,
                )

                assistant_message = self.llm.get_message_content(final_response)
                if assistant_message:
                    # Ensure act_as is not None (default to 'assistant' if missing)
                    role = (
                        self.act_as
                        if self.act_as is not None
                        else MessageType.ASSISTANT
                    )
                    self.add_to_history(AssistantMessage(content=assistant_message))
                    return self.conversation_history

                return f'The final result based on the tool executions is: {function_response}'

            except Exception as e:
                retry_count += 1
                context = {
                    'conversation_history': self.conversation_history,
                    'attempt': retry_count,
                }

                should_retry, analysis = await self.handle_error(e, context)
                if should_retry and retry_count <= self.max_retries:
                    # Record retry
                    agent_metrics.record_retry(self.name, 'execution_error')

                    self.add_to_history(
                        AssistantMessage(
                            content=f'Error occurred. Analysis: {analysis}'
                        )
                    )
                    continue

                raise AgentError(
                    f'Failed after {retry_count} attempts. Last error: {analysis}',
                    original_error=e,
                )

        raise AgentError(f'Failed after maximum {self.max_retries} attempts.')

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

            is_final = 'FINAL' in analysis
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
