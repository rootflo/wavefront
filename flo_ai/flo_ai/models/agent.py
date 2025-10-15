import json
from typing import Dict, Any, List, Optional
from flo_ai.models.base_agent import BaseAgent, AgentType, ReasoningPattern
from flo_ai.llm.base_llm import BaseLLM, ImageMessage
from flo_ai.models.document import DocumentMessage
from flo_ai.tool.base_tool import Tool, ToolExecutionError
from flo_ai.models.agent_error import AgentError
from flo_ai.utils.logger import logger
from flo_ai.utils.variable_extractor import (
    extract_variables_from_inputs,
    extract_agent_variables,
    validate_multi_agent_variables,
    resolve_variables,
)


class Agent(BaseAgent):
    def __init__(
        self,
        name: str,
        system_prompt: str,
        llm: BaseLLM,
        tools: Optional[List[Tool]] = None,
        max_retries: int = 3,
        reasoning_pattern: ReasoningPattern = ReasoningPattern.DIRECT,
        output_schema: Optional[Dict[str, Any]] = None,
        role: Optional[str] = None,
    ):
        # Determine agent type based on tools
        agent_type = AgentType.TOOL_USING if tools else AgentType.CONVERSATIONAL

        # Enhance system prompt with role if provided
        enhanced_prompt = system_prompt
        if role:
            enhanced_prompt = f'You are {role}. {system_prompt}'

        super().__init__(
            name=name,
            system_prompt=enhanced_prompt,
            agent_type=agent_type,
            llm=llm,
            max_retries=max_retries,
        )
        self.tools = tools or []
        self.tools_dict = {tool.name: tool for tool in self.tools}
        self.reasoning_pattern = reasoning_pattern
        self.output_schema = output_schema
        self.role = role

    async def run(
        self,
        inputs: List[str | ImageMessage | DocumentMessage] | str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> str:
        variables = variables or {}

        if isinstance(inputs, str):
            inputs = [inputs]

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
                if isinstance(input, ImageMessage):
                    self.add_to_history('user', self.llm.format_image_in_message(input))
                elif isinstance(input, DocumentMessage):
                    formatted_doc = await self.llm.format_document_in_message(input)
                    self.add_to_history('user', formatted_doc)
                else:
                    # Resolve variables in text input
                    resolved_input = resolve_variables(input, variables)
                    self.add_to_history('user', resolved_input)

            # after resolving agent system prompts and inputs, mark variables as resolved
            self.resolved_variables = True

        else:
            # Variables already resolved, process inputs without variable resolution
            for input in inputs:
                if isinstance(input, ImageMessage):
                    self.add_to_history('user', self.llm.format_image_in_message(input))
                elif isinstance(input, DocumentMessage):
                    formatted_doc = await self.llm.format_document_in_message(input)
                    self.add_to_history('user', formatted_doc)
                else:
                    self.add_to_history('user', input)

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

                messages = [
                    {
                        'role': 'system',
                        'content': system_content,
                    }
                ] + self.conversation_history

                logger.debug('Sending messages to LLM:', messages)
                response = await self.llm.generate(
                    messages, output_schema=self.output_schema
                )
                logger.debug('Raw LLM Response:', response)

                assistant_message = self.llm.get_message_content(response)
                logger.debug('Extracted message:', assistant_message)

                if assistant_message:
                    self.add_to_history('assistant', assistant_message)
                    return assistant_message
                else:
                    possible_tool_message = await self.llm.get_function_call(response)
                    if possible_tool_message:
                        return possible_tool_message['arguments']
                    logger.debug('Warning: No message content found in response')
                    return None

            except Exception as e:
                retry_count += 1
                context = {
                    'conversation_history': self.conversation_history,
                    'attempt': retry_count,
                }

                should_retry, analysis = await self.handle_error(e, context)

                if should_retry and retry_count <= self.max_retries:
                    self.add_to_history(
                        'system', f'Error occurred. Analysis: {analysis}'
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

        while retry_count <= self.max_retries:
            try:
                # Resolve variables in system prompt based on reasoning pattern
                if self.reasoning_pattern == ReasoningPattern.REACT:
                    system_content = self._get_react_prompt(variables)
                elif self.reasoning_pattern == ReasoningPattern.COT:
                    system_content = self._get_cot_prompt(variables)
                else:
                    system_content = resolve_variables(self.system_prompt, variables)

                messages = [
                    {
                        'role': 'system',
                        'content': system_content,
                    }
                ] + self.conversation_history

                # Keep executing tools until we get a final answer
                max_tool_calls = 5  # Limit the number of tool calls per query
                tool_call_count = 0

                while tool_call_count < max_tool_calls:
                    formatted_tools = self.llm.format_tools_for_llm(self.tools)
                    response = await self.llm.generate(
                        messages,
                        functions=formatted_tools,
                        output_schema=self.output_schema,
                    )

                    # Handle ReACT and CoT patterns
                    function_call = await self.llm.get_function_call(response)

                    # If no function call, we have our final answer
                    if not function_call:
                        assistant_message = self.llm.get_message_content(response)
                        if assistant_message:
                            self.add_to_history('assistant', assistant_message)
                            return assistant_message
                        break

                    # Execute the tool
                    try:
                        function_name = function_call['name']
                        if isinstance(function_call['arguments'], str):
                            function_args = json.loads(function_call['arguments'])
                        else:
                            function_args = function_call['arguments']

                        tool = self.tools_dict[function_name]
                        # function_response = await tool.execute(**function_args)
                        function_response = await tool.run(
                            inputs=[], variables=None, **function_args
                        )
                        tool_call_count += 1

                        # Add function call to history
                        self.add_to_history(
                            'function',
                            f'Tool response: {str(function_response)}',
                            name=function_name,
                        )

                        # Add the function response to messages for context
                        messages.append(
                            {
                                'role': 'function',
                                'name': function_name,
                                'content': f'Here is the result of the tool call: \n {str(function_response)}',
                            }
                        )

                        # Add a prompt to continue the reasoning
                        messages.append(
                            {
                                'role': 'user',
                                'content': 'Continue with your reasoning based on this result. What should be done next?',
                            }
                        )

                    except (json.JSONDecodeError, KeyError, ToolExecutionError) as e:
                        retry_count += 1
                        context = {
                            'function_call': function_call,
                            'attempt': retry_count,
                        }
                        should_retry, analysis = await self.handle_error(e, context)
                        if should_retry and retry_count <= self.max_retries:
                            self.add_to_history(
                                'system', f'Tool execution error: {analysis}'
                            )
                            continue
                        raise AgentError(
                            f'Tool execution failed: {analysis}', original_error=e
                        )

                # Generate final response if we've hit the tool call limit or exited the loop
                final_response = await self.llm.generate(
                    messages
                    + [
                        {
                            'role': 'system',
                            'content': 'Please provide a final answer based on all the tool results above.',
                        }
                    ],
                    output_schema=self.output_schema,
                )

                assistant_message = self.llm.get_message_content(final_response)
                if assistant_message:
                    self.add_to_history('assistant', assistant_message)
                    return assistant_message

                return f'The final result based on the tool executions is: {function_response}'

            except Exception as e:
                retry_count += 1
                context = {
                    'conversation_history': self.conversation_history,
                    'attempt': retry_count,
                }

                should_retry, analysis = await self.handle_error(e, context)
                if should_retry and retry_count <= self.max_retries:
                    self.add_to_history(
                        'system', f'Error occurred. Analysis: {analysis}'
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

            Available tools:
            {tools_desc}

            Remember to:
            1. Think carefully about what needs to be done
            2. Use tools when needed
            3. Make observations about tool results
            4. Conclude with a final answer when the task is complete"""

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
            5. End with a final, well-justified answer"""

        return cot_prompt
