"""
LLM-Powered Router Functions for Arium Workflows

This module provides intelligent routing capabilities using Large Language Models
to make dynamic routing decisions based on conversation context and history.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Callable, Any, Union, get_args, List
from functools import wraps
from flo_ai.arium.memory import BaseMemory, ExecutionPlan, StepStatus
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.llm import OpenAI
from flo_ai.utils.logger import logger


class BaseLLMRouter(ABC):
    """
    Base class for LLM-powered routers that make intelligent routing decisions
    based on conversation context and history.
    """

    def __init__(
        self,
        llm: Optional[BaseLLM] = None,
        temperature: float = 0.1,
        max_retries: int = 3,
        fallback_strategy: str = 'first',
    ):
        """
        Initialize the LLM router.

        Args:
            llm: The LLM instance to use for routing decisions. Defaults to GPT-4o-mini.
            temperature: Temperature for LLM calls (lower = more deterministic)
            max_retries: Maximum number of retries for LLM calls
            fallback_strategy: Strategy when LLM fails ("first", "last", "random")
        """
        self.llm = llm or OpenAI(model='gpt-4o-mini', temperature=temperature)
        self.temperature = temperature
        self.max_retries = max_retries
        self.fallback_strategy = fallback_strategy
        self.supports_self_reference = (
            False  # Most routers don't support self-reference by default
        )

    @abstractmethod
    def get_routing_options(self) -> Dict[str, str]:
        """
        Return a dictionary mapping route names to their descriptions.

        Returns:
            Dict[str, str]: Mapping of route names to descriptions
        """
        pass

    @abstractmethod
    def get_routing_prompt(
        self,
        memory: BaseMemory,
        options: Dict[str, str],
        execution_context: dict = None,
    ) -> str:
        """
        Generate the prompt for the LLM to make routing decisions.

        Args:
            memory: The conversation memory
            options: Available routing options with descriptions

        Returns:
            str: The prompt for the LLM
        """
        pass

    def get_fallback_route(self, options: Dict[str, str]) -> str:
        """
        Get fallback route when LLM fails.

        Args:
            options: Available routing options

        Returns:
            str: The fallback route name
        """
        routes = list(options.keys())

        if self.fallback_strategy == 'first':
            return routes[0]
        elif self.fallback_strategy == 'last':
            return routes[-1]
        elif self.fallback_strategy == 'random':
            import random

            return random.choice(routes)
        else:
            return routes[0]

    async def route(self, memory: BaseMemory, execution_context: dict = None) -> str:
        """
        Make a routing decision using the LLM.

        Args:
            memory: The conversation memory

        Returns:
            str: The name of the route to take
        """
        options = self.get_routing_options()

        for attempt in range(self.max_retries):
            try:
                prompt = self.get_routing_prompt(memory, options, execution_context)

                messages = [{'role': 'user', 'content': prompt}]
                response = await self.llm.generate(messages)
                decision = self.llm.get_message_content(response).strip().lower()

                # Find matching option (case-insensitive)
                for option_name in options:
                    if (
                        option_name.lower() == decision
                        or option_name.lower() in decision
                    ):
                        logger.info(f'LLM router selected: {option_name}')
                        return option_name

                # If no exact match, try partial matching
                for option_name in options:
                    if (
                        decision in option_name.lower()
                        or option_name.lower() in decision
                    ):
                        logger.info(
                            f'LLM router selected (partial match): {option_name}'
                        )
                        return option_name

                logger.warning(
                    f"LLM router attempt {attempt + 1}: Invalid decision '{decision}', retrying..."
                )

            except Exception as e:
                logger.error(f'LLM router attempt {attempt + 1} failed: {e}')

        # Fallback strategy
        fallback = self.get_fallback_route(options)
        logger.warning(f'LLM router failed, using fallback: {fallback}')
        return fallback


class SmartRouter(BaseLLMRouter):
    """
    A general-purpose smart router that can route between different types of agents
    based on task analysis and conversation context.
    """

    def __init__(
        self,
        routing_options: Dict[str, str],
        llm: Optional[BaseLLM] = None,
        context_description: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize the smart router.

        Args:
            routing_options: Dict mapping route names to descriptions
            llm: LLM instance for routing decisions
            context_description: Additional context about the workflow
            **kwargs: Additional arguments for BaseLLMRouter
        """
        super().__init__(llm=llm, **kwargs)
        self.routing_options = routing_options
        self.context_description = context_description or 'a multi-agent workflow'

    def get_routing_options(self) -> Dict[str, str]:
        return self.routing_options

    def get_routing_prompt(
        self,
        memory: BaseMemory,
        options: Dict[str, str],
        execution_context: dict = None,
    ) -> str:
        conversation = memory.get()

        # Format conversation history with smart truncation
        if isinstance(conversation, list):
            # Start with last message and add more if we have space
            messages = conversation[-5:]  # Last 5 messages
            conversation_text = self._truncate_conversation_for_tokens(messages)
        else:
            conversation_text = str(conversation)

        # Format options
        options_text = '\n'.join(
            [f'- {name}: {desc}' for name, desc in options.items()]
        )

        # Add execution context if available
        context_info = ''
        if execution_context:
            visit_counts = execution_context.get('node_visit_count', {})
            current_node = execution_context.get('current_node', 'unknown')
            iteration = execution_context.get('iteration_count', 0)

            # Create visit count warning if any node has been visited multiple times
            visit_warnings = []
            for node_name, count in visit_counts.items():
                if count >= 2:
                    visit_warnings.append(f'- {node_name}: visited {count} times')

            if visit_warnings:
                context_info = f"""

⚠️  EXECUTION CONTEXT (Avoid Infinite Loops):
Current iteration: {iteration}
Current node: {current_node}
Node visit counts:
{chr(10).join(visit_warnings)}

IMPORTANT: To prevent infinite loops, strongly prefer moving to different nodes or completing the workflow.
"""

        prompt = f"""You are a workflow coordinator for {self.context_description}.

Based on the conversation history below, decide which agent should handle the next step.
{context_info}
Available agents:
{options_text}

Recent conversation:
{conversation_text}

Instructions:
1. Analyze the conversation to understand what type of work is needed next
2. Choose the most appropriate agent from the available options
3. If you notice nodes being visited repeatedly, prefer different options or completion
4. Respond with ONLY the agent name (no explanations or additional text)

Agent to route to:"""

        return prompt

    def _truncate_conversation_for_tokens(
        self, messages: List[Any], max_tokens: int = 128000
    ) -> str:
        """
        Intelligently truncate conversation to fit within token limits.
        Prioritizes recent messages while ensuring we don't exceed token limits.
        """
        if not messages:
            return ''

        # Start with the most recent message
        truncated_messages = [messages[-1]]
        current_text = str(messages[-1])

        # Add older messages if we have space
        for msg in reversed(messages[:-1]):
            msg_text = str(msg)
            # Rough token estimation (4 chars per token is a common approximation)
            estimated_tokens = len(current_text + '\n' + msg_text) // 4

            if estimated_tokens <= max_tokens:
                truncated_messages.insert(0, msg)
                current_text = '\n'.join([str(m) for m in truncated_messages])
            else:
                break

        return '\n'.join([str(msg) for msg in truncated_messages])


class TaskClassifierRouter(BaseLLMRouter):
    """
    A router specialized for classifying tasks and routing to appropriate specialists.
    """

    def __init__(
        self,
        task_categories: Dict[str, Dict[str, Any]],
        llm: Optional[BaseLLM] = None,
        **kwargs,
    ):
        """
        Initialize the task classifier router.

        Args:
            task_categories: Dict mapping category names to their config:
                {
                    "category_name": {
                        "description": "What this category handles",
                        "keywords": ["keyword1", "keyword2"],  # Optional
                        "examples": ["example task 1", "example task 2"]  # Optional
                    }
                }
            llm: LLM instance for routing decisions
            **kwargs: Additional arguments for BaseLLMRouter
        """
        super().__init__(llm=llm, **kwargs)
        self.task_categories = task_categories

    def get_routing_options(self) -> Dict[str, str]:
        return {
            name: config['description'] for name, config in self.task_categories.items()
        }

    def get_routing_prompt(
        self,
        memory: BaseMemory,
        options: Dict[str, str],
        execution_context: dict = None,
    ) -> str:
        conversation = memory.get()

        # Get the latest user input or task
        if isinstance(conversation, list) and conversation:
            latest_task = str(conversation[-1])
        else:
            latest_task = str(conversation)

        # Build detailed category descriptions
        categories_detail = []
        for name, config in self.task_categories.items():
            detail = f"- {name}: {config['description']}"

            if 'keywords' in config:
                detail += f"\n  Keywords: {', '.join(config['keywords'])}"

            if 'examples' in config:
                detail += f"\n  Examples: {', '.join(config['examples'])}"

            categories_detail.append(detail)

        categories_text = '\n\n'.join(categories_detail)

        prompt = f"""You are a task classifier that routes requests to specialized agents.

Task to classify:
{latest_task}

Available categories:
{categories_text}

Instructions:
1. Analyze the task to understand what type of work it requires
2. Choose the most appropriate category from the available options
3. Consider keywords and examples to make the best match
4. Respond with ONLY the category name (no explanations)

Category:"""

        return prompt


class ReflectionRouter(BaseLLMRouter):
    """
    A router designed for reflection patterns like A -> B -> A -> C.
    Commonly used for main -> critic -> main -> final workflows where B is a reflection/critique step.
    Uses execution context to determine flow state and make intelligent routing decisions.
    """

    def __init__(
        self,
        flow_pattern: List[str],
        llm: Optional[BaseLLM] = None,
        allow_early_exit: bool = False,
        **kwargs,
    ):
        """
        Initialize the reflection router.

        Args:
            flow_pattern: List of node names defining the reflection pattern (e.g., ["main", "critic", "main", "final"])
            llm: LLM instance for routing decisions
            allow_early_exit: Whether to allow LLM to exit pattern early if appropriate
            **kwargs: Additional arguments for BaseLLMRouter
        """
        super().__init__(llm=llm, **kwargs)
        self.flow_pattern = flow_pattern
        self.allow_early_exit = allow_early_exit
        self.supports_self_reference = (
            True  # ReflectionRouter can return to the same node
        )

    def get_routing_options(self) -> Dict[str, str]:
        """Get available routing options based on flow pattern"""
        unique_nodes = list(
            dict.fromkeys(self.flow_pattern)
        )  # Preserve order, remove duplicates

        # Generate descriptions based on reflection pattern
        options = {}
        for node in unique_nodes:
            # Count occurrences and positions in pattern
            positions = [i for i, x in enumerate(self.flow_pattern) if x == node]
            if len(positions) > 1:
                options[node] = (
                    f"Step {positions} in the reflection pattern: {' -> '.join(self.flow_pattern)}"
                )
            else:
                options[node] = (
                    f"Step {positions[0] + 1} in the reflection pattern: {' -> '.join(self.flow_pattern)}"
                )

        return options

    def _get_next_step_in_pattern(self, execution_context: dict) -> Optional[str]:
        """Determine the next step in the reflection pattern based on execution context"""
        if not execution_context:
            return self.flow_pattern[0] if self.flow_pattern else None

        visit_counts = execution_context.get('node_visit_count', {})
        current_node = execution_context.get('current_node', '')

        # Find the current position in the pattern
        try:
            # Find where we are in the reflection pattern
            current_step = -1
            for i, node in enumerate(self.flow_pattern):
                node_visits = visit_counts.get(node, 0)

                # For nodes that appear multiple times, we need to track which occurrence
                if node == current_node:
                    # Count how many times this node should have been visited at this step
                    expected_visits = len(
                        [x for x in self.flow_pattern[: i + 1] if x == node]
                    )
                    if node_visits >= expected_visits:
                        current_step = i

            # Determine next step
            next_step_index = current_step + 1
            if next_step_index < len(self.flow_pattern):
                return self.flow_pattern[next_step_index]
            else:
                # Pattern completed
                return None

        except Exception:
            # Fallback to first step
            return self.flow_pattern[0] if self.flow_pattern else None

    def get_routing_prompt(
        self,
        memory: BaseMemory,
        options: Dict[str, str],
        execution_context: dict = None,
    ) -> str:
        conversation = memory.get()

        # Format conversation history
        if isinstance(conversation, list):
            conversation_text = '\n'.join(
                [str(msg) for msg in conversation[-3:]]
            )  # Last 3 messages for flow context
        else:
            conversation_text = str(conversation)

        # Determine suggested next step based on reflection pattern
        suggested_next = self._get_next_step_in_pattern(execution_context)

        # Format options
        options_text = '\n'.join(
            [f'- {name}: {desc}' for name, desc in options.items()]
        )

        # Add execution context info
        context_info = ''
        if execution_context:
            visit_counts = execution_context.get('node_visit_count', {})
            current_node = execution_context.get('current_node', 'unknown')
            iteration = execution_context.get('iteration_count', 0)

            # Show reflection pattern progress
            pattern_progress = []
            for i, node in enumerate(self.flow_pattern):
                visits = visit_counts.get(node, 0)
                expected_visits = len(
                    [x for x in self.flow_pattern[: i + 1] if x == node]
                )
                status = '✓' if visits >= expected_visits else '○'
                pattern_progress.append(f'{status} {node}')

            context_info = f"""
📋 REFLECTION PATTERN: {' → '.join(self.flow_pattern)}
📍 CURRENT PROGRESS: {' → '.join(pattern_progress)}
🎯 SUGGESTED NEXT: {suggested_next or 'Pattern Complete'}
💡 CURRENT NODE: {current_node} (iteration {iteration})
"""

        # Create prompt based on whether early exit is allowed
        if self.allow_early_exit:
            prompt = f"""You are a reflection coordinator managing this workflow pattern: {' → '.join(self.flow_pattern)}

{context_info}
Available options:
{options_text}

Recent conversation:
{conversation_text}

Instructions:
1. Follow the reflection pattern: {' → '.join(self.flow_pattern)}
2. The suggested next step is: {suggested_next or 'Pattern Complete'}
3. You may exit early if the reflection cycle is complete
4. Consider conversation context and reflection progress
5. Respond with ONLY the agent name (no explanations)

Next agent:"""
        else:
            prompt = f"""You are a reflection coordinator managing this strict reflection pattern: {' → '.join(self.flow_pattern)}

{context_info}
Available options:
{options_text}

Recent conversation:
{conversation_text}

Instructions:
1. STRICTLY follow the reflection pattern: {' → '.join(self.flow_pattern)}
2. The next step should be: {suggested_next or 'Pattern Complete'}
3. Do not deviate from the pattern unless absolutely necessary
4. Respond with ONLY the agent name (no explanations)

Next agent:"""

        return prompt


class PlanExecuteRouter(BaseLLMRouter):
    """
    A router that implements plan-and-execute patterns like Cursor.
    Creates execution plans and routes through steps sequentially.
    """

    def __init__(
        self,
        agents: Dict[str, str],  # agent_name -> description mapping
        planner_agent: str = 'planner',
        executor_agent: str = 'executor',
        reviewer_agent: Optional[str] = None,
        llm: Optional[BaseLLM] = None,
        max_retries: int = 3,
        **kwargs,
    ):
        """
        Initialize the plan-execute router.

        Args:
            agents: Dict mapping agent names to their descriptions/capabilities
            planner_agent: Name of the agent responsible for creating plans
            executor_agent: Name of the agent responsible for executing steps
            reviewer_agent: Optional name of the agent responsible for reviewing results
            llm: LLM instance for routing decisions
            max_retries: Maximum retries for step execution
            **kwargs: Additional arguments for BaseLLMRouter
        """
        super().__init__(llm=llm, **kwargs)
        self.agents = agents
        self.planner_agent = planner_agent
        self.executor_agent = executor_agent
        self.reviewer_agent = reviewer_agent
        self.max_retries = max_retries
        self.supports_self_reference = (
            True  # Can route to same agent for iterative execution
        )

    def get_routing_options(self) -> Dict[str, str]:
        """Get available routing options based on configured agents"""
        return self.agents

    def get_routing_prompt(
        self,
        memory: BaseMemory,
        options: Dict[str, str],
        execution_context: dict = None,
    ) -> str:
        conversation = memory.get()

        # Format conversation history
        if isinstance(conversation, list):
            conversation_text = '\n'.join(
                [str(msg) for msg in conversation[-3:]]
            )  # Last 3 messages for context
        else:
            conversation_text = str(conversation)

        # Check if we have a plan in memory
        current_plan = (
            memory.get_current_plan() if hasattr(memory, 'get_current_plan') else None
        )

        if current_plan is None:
            # No plan exists - route to planner
            return self._create_planning_prompt(conversation_text, options)
        else:
            # Plan exists - determine next action based on plan state
            return self._create_execution_prompt(
                current_plan, conversation_text, options, execution_context
            )

    def _create_planning_prompt(
        self, conversation_text: str, options: Dict[str, str]
    ) -> str:
        """Create prompt for initial planning phase"""
        options_text = '\n'.join(
            [f'- {name}: {desc}' for name, desc in options.items()]
        )

        prompt = f"""You are coordinating a plan-and-execute workflow. No execution plan exists yet.

Available agents:
{options_text}

Recent conversation:
{conversation_text}

TASK: Create an execution plan by routing to the {self.planner_agent}.

Instructions:
1. Route to "{self.planner_agent}" to create a detailed execution plan
2. The planner will break down the task into sequential steps
3. Each step will specify which agent should execute it
4. Respond with ONLY the agent name: {self.planner_agent}

Next agent:"""

        return prompt

    def _create_execution_prompt(
        self,
        plan: ExecutionPlan,
        conversation_text: str,
        options: Dict[str, str],
        execution_context: dict = None,
    ) -> str:
        """Create prompt for execution phase based on current plan state"""

        # Get next steps that are ready to execute
        next_steps = plan.get_next_steps()

        # Format plan progress
        progress_lines = []
        for step in plan.steps:
            status_icon = {
                StepStatus.PENDING: '○',
                StepStatus.IN_PROGRESS: '⏳',
                StepStatus.COMPLETED: '✅',
                StepStatus.FAILED: '❌',
                StepStatus.SKIPPED: '⏭️',
            }.get(step.status, '○')
            progress_lines.append(
                f'{status_icon} {step.id}: {step.description} (→ {step.agent})'
            )

        progress_text = '\n'.join(progress_lines)

        # Determine what to do next
        if plan.is_completed():
            # All steps completed
            if self.reviewer_agent and self.reviewer_agent in options:
                action = f'Route to {self.reviewer_agent} for final review'
                suggested_agent = self.reviewer_agent
            else:
                action = 'Plan completed - route to any agent for final output'
                suggested_agent = next(iter(options.keys()))  # First available agent
        elif plan.has_failed_steps():
            # Some steps failed - need recovery
            failed_steps = [
                step for step in plan.steps if step.status == StepStatus.FAILED
            ]
            failed_step = failed_steps[0]  # Focus on first failed step
            action = f"Handle failed step '{failed_step.id}' - route to {failed_step.agent} for retry"
            suggested_agent = failed_step.agent
        elif next_steps:
            # There are steps ready to execute
            next_step = next_steps[0]  # Execute first ready step
            action = f"Execute step '{next_step.id}' - route to {next_step.agent}"
            suggested_agent = next_step.agent
        else:
            # Waiting for dependencies
            action = f'Waiting for dependencies - route to {self.executor_agent} for status check'
            suggested_agent = self.executor_agent

        options_text = '\n'.join(
            [f'- {name}: {desc}' for name, desc in options.items()]
        )

        # Add execution context info
        context_info = ''
        if execution_context:
            current_node = execution_context.get('current_node', 'unknown')
            iteration = execution_context.get('iteration_count', 0)

            context_info = f"""
💡 EXECUTION CONTEXT:
Current node: {current_node} (iteration {iteration})
"""

        prompt = f"""You are coordinating plan execution in a plan-and-execute workflow.

📋 EXECUTION PLAN: {plan.title}
{plan.description}

📊 CURRENT PROGRESS:
{progress_text}

🎯 NEXT ACTION: {action}
🎯 SUGGESTED AGENT: {suggested_agent}
{context_info}
Available agents:
{options_text}

Recent conversation:
{conversation_text}

Instructions:
1. Follow the execution plan step by step
2. Route to the suggested agent: {suggested_agent}
3. Each agent will execute their assigned step
4. Continue until all steps are completed
5. Respond with ONLY the agent name (no explanations)

Next agent:"""

        return prompt


class ConversationAnalysisRouter(BaseLLMRouter):
    """
    A router that analyzes conversation flow and context to make routing decisions.
    """

    def __init__(
        self,
        routing_logic: Dict[str, str],
        analysis_depth: int = 3,
        llm: Optional[BaseLLM] = None,
        **kwargs,
    ):
        """
        Initialize the conversation analysis router.

        Args:
            routing_logic: Dict mapping route names to routing criteria
            analysis_depth: Number of recent messages to analyze
            llm: LLM instance for routing decisions
            **kwargs: Additional arguments for BaseLLMRouter
        """
        super().__init__(llm=llm, **kwargs)
        self.routing_logic = routing_logic
        self.analysis_depth = analysis_depth

    def get_routing_options(self) -> Dict[str, str]:
        return self.routing_logic

    def get_routing_prompt(
        self,
        memory: BaseMemory,
        options: Dict[str, str],
        execution_context: dict = None,
    ) -> str:
        conversation = memory.get()

        # Analyze recent conversation
        if isinstance(conversation, list):
            recent_messages = conversation[-self.analysis_depth :]
            conversation_text = '\n'.join(
                [f'Message {i+1}: {msg}' for i, msg in enumerate(recent_messages)]
            )
        else:
            conversation_text = str(conversation)

        # Format routing logic
        logic_text = '\n'.join(
            [f'- {name}: {criteria}' for name, criteria in options.items()]
        )

        # Add execution context if available
        context_info = ''
        if execution_context:
            visit_counts = execution_context.get('node_visit_count', {})
            current_node = execution_context.get('current_node', 'unknown')
            iteration = execution_context.get('iteration_count', 0)

            # Create visit count warning if any node has been visited multiple times
            visit_warnings = []
            for node_name, count in visit_counts.items():
                if count >= 2:
                    visit_warnings.append(f'- {node_name}: visited {count} times')

            if visit_warnings:
                context_info = f"""

⚠️  EXECUTION CONTEXT (Avoid Infinite Loops):
Current iteration: {iteration}
Current node: {current_node}
Node visit counts:
{chr(10).join(visit_warnings)}

CRITICAL: Excessive node revisits detected! Consider completing the workflow or choosing different paths.
"""

        prompt = f"""You are a conversation flow analyzer that determines the next step in a workflow.

Recent conversation (last {self.analysis_depth} messages):
{conversation_text}
{context_info}
Routing logic:
{logic_text}

Instructions:
1. Analyze the conversation flow and current state
2. Consider what has been accomplished and what needs to happen next
3. If nodes are being revisited too frequently, strongly prefer completion or different paths
4. Choose the route that best matches the current conversation state
5. Respond with ONLY the route name (no explanations)

Next route:"""

        return prompt


def create_llm_router(router_type: str, **config) -> Callable[[BaseMemory], str]:
    """
    Factory function to create LLM-powered routers with different configurations.

    Args:
        router_type: Type of router ("smart", "task_classifier", "conversation_analysis", "reflection", "plan_execute")
        **config: Configuration specific to the router type

    Returns:
        Callable router function that can be used in Arium workflows

    Examples:
        # Smart router
        router = create_llm_router(
            "smart",
            routing_options={
                "researcher": "Gather information and conduct research",
                "analyst": "Analyze data and perform calculations",
                "writer": "Create reports and summaries"
            }
        )

        # Task classifier router
        router = create_llm_router(
            "task_classifier",
            task_categories={
                "research": {
                    "description": "Research and information gathering tasks",
                    "keywords": ["research", "find", "investigate", "gather"],
                    "examples": ["Find information about...", "Research the topic of..."]
                },
                "analysis": {
                    "description": "Data analysis and computational tasks",
                    "keywords": ["analyze", "calculate", "compute", "data"],
                    "examples": ["Analyze the data...", "Calculate the..."]
                }
            }
        )

        # Reflection router for A -> B -> A -> C patterns
        router = create_llm_router(
            "reflection",
            flow_pattern=["main_agent", "critic", "main_agent", "final_agent"],
            allow_early_exit=False
        )

        # Plan-Execute router for Cursor-style workflows
        router = create_llm_router(
            "plan_execute",
            agents={
                "planner": "Creates detailed execution plans",
                "developer": "Implements code and features",
                "tester": "Tests implementations",
                "reviewer": "Reviews final results"
            },
            planner_agent="planner",
            executor_agent="developer"
        )
    """

    if router_type == 'smart':
        if 'routing_options' not in config:
            raise ValueError("SmartRouter requires 'routing_options' parameter")

        router_instance = SmartRouter(**config)

    elif router_type == 'task_classifier':
        if 'task_categories' not in config:
            raise ValueError(
                "TaskClassifierRouter requires 'task_categories' parameter"
            )

        router_instance = TaskClassifierRouter(**config)

    elif router_type == 'conversation_analysis':
        if 'routing_logic' not in config:
            raise ValueError(
                "ConversationAnalysisRouter requires 'routing_logic' parameter"
            )

        router_instance = ConversationAnalysisRouter(**config)

    elif router_type == 'reflection':
        if 'flow_pattern' not in config:
            raise ValueError("ReflectionRouter requires 'flow_pattern' parameter")

        router_instance = ReflectionRouter(**config)

    elif router_type == 'plan_execute':
        if 'agents' not in config:
            raise ValueError("PlanExecuteRouter requires 'agents' parameter")

        router_instance = PlanExecuteRouter(**config)

    else:
        raise ValueError(f'Unknown router type: {router_type}')

    # Get the routing options for type annotation
    options = router_instance.get_routing_options()
    option_names = tuple(options.keys())

    # Create proper Literal type for validation
    from typing import Literal

    if len(option_names) == 1:
        # Handle single option case
        literal_type = Literal[option_names[0]]
    else:
        # Handle multiple options case
        literal_type = Literal[option_names]

    # Return a function that can be used as a router
    async def router_function(memory: BaseMemory, execution_context: dict = None):
        """Generated router function that uses LLM for routing decisions"""
        return await router_instance.route(memory, execution_context)

    # Add proper type annotations for validation
    router_function.__annotations__ = {'memory': BaseMemory, 'return': literal_type}

    # Transfer router instance attributes to the function for validation
    router_function.supports_self_reference = getattr(
        router_instance, 'supports_self_reference', False
    )

    return router_function


def llm_router(
    routing_options: Dict[str, str],
    llm: Optional[BaseLLM] = None,
    context_description: Optional[str] = None,
    **kwargs,
):
    """
    Decorator to create LLM-powered routers with a simple interface.

    Args:
        routing_options: Dict mapping route names to descriptions
        llm: LLM instance for routing decisions
        context_description: Additional context about the workflow
        **kwargs: Additional router configuration

    Returns:
        Decorator function

    Example:
        @llm_router({
            "researcher": "Gather information and conduct research",
            "analyst": "Analyze data and perform calculations",
            "writer": "Create reports and summaries"
        })
        def my_smart_router(memory: BaseMemory) -> Literal["researcher", "analyst", "writer"]:
            pass  # Implementation is provided by decorator
    """

    def decorator(func):
        # Extract return type annotation to validate routing options
        if hasattr(func, '__annotations__') and 'return' in func.__annotations__:
            return_annotation = func.__annotations__['return']

            # Validate that routing options match the return type
            if (
                hasattr(return_annotation, '__origin__')
                and return_annotation.__origin__ is Union
            ):
                # Handle Literal types
                args = get_args(return_annotation)
                if args and hasattr(args[0], '__origin__'):
                    literal_values = get_args(args[0])
                    option_keys = set(routing_options.keys())
                    literal_set = set(literal_values)

                    if option_keys != literal_set:
                        logger.warning(
                            f"Routing options {option_keys} don't match return type {literal_set}"
                        )

        # Create the router instance
        router_instance = SmartRouter(
            routing_options=routing_options,
            llm=llm,
            context_description=context_description,
            **kwargs,
        )

        @wraps(func)
        async def wrapper(memory: BaseMemory, execution_context: dict = None):
            return await router_instance.route(memory, execution_context)

        # Preserve the original function's type annotations including return type
        wrapper.__annotations__ = func.__annotations__.copy()

        # Ensure the return annotation is properly set
        if 'return' in func.__annotations__:
            wrapper.__annotations__['return'] = func.__annotations__['return']

        return wrapper

    return decorator


# Convenience functions for common routing patterns


def create_research_analysis_router(
    research_agent: str = 'researcher',
    analysis_agent: str = 'analyst',
    summary_agent: str = 'summarizer',
    llm: Optional[BaseLLM] = None,
) -> Callable[[BaseMemory], str]:
    """
    Create a router for common research -> analysis -> summary workflows.

    Args:
        research_agent: Name of the research agent
        analysis_agent: Name of the analysis agent
        summary_agent: Name of the summary agent
        llm: LLM instance for routing decisions

    Returns:
        Router function for research/analysis workflows
    """
    return create_llm_router(
        'task_classifier',
        task_categories={
            research_agent: {
                'description': 'Research and information gathering tasks',
                'keywords': [
                    'research',
                    'find',
                    'investigate',
                    'gather',
                    'search',
                    'lookup',
                ],
                'examples': [
                    'Find information about...',
                    'Research the topic of...',
                    'Gather data on...',
                ],
            },
            analysis_agent: {
                'description': 'Data analysis and computational tasks',
                'keywords': [
                    'analyze',
                    'calculate',
                    'compute',
                    'data',
                    'numbers',
                    'statistics',
                ],
                'examples': [
                    'Analyze the data...',
                    'Calculate the...',
                    'Compute statistics for...',
                ],
            },
            summary_agent: {
                'description': 'Summarization and conclusion tasks',
                'keywords': [
                    'summarize',
                    'conclude',
                    'report',
                    'final',
                    'overview',
                    'wrap up',
                ],
                'examples': [
                    'Summarize the findings...',
                    'Create a final report...',
                    'Conclude the analysis...',
                ],
            },
        },
        llm=llm,
    )


def create_main_critic_reflection_router(
    main_agent: str = 'main_agent',
    critic_agent: str = 'critic',
    final_agent: str = 'final_agent',
    allow_early_exit: bool = False,
    llm: Optional[BaseLLM] = None,
) -> Callable[[BaseMemory], str]:
    """
    Create a router for the A -> B -> A -> C reflection pattern (main -> critic -> main -> final).

    Args:
        main_agent: Name of the main agent (appears twice in pattern)
        critic_agent: Name of the critic agent for reflection
        final_agent: Name of the final agent
        allow_early_exit: Whether to allow LLM to exit reflection early if appropriate
        llm: LLM instance for routing decisions

    Returns:
        Router function for main/critic/final reflection workflows
    """
    return create_llm_router(
        'reflection',
        flow_pattern=[main_agent, critic_agent, main_agent, final_agent],
        allow_early_exit=allow_early_exit,
        llm=llm,
    )


def create_plan_execute_router(
    planner_agent: str = 'planner',
    executor_agent: str = 'executor',
    reviewer_agent: Optional[str] = None,
    additional_agents: Optional[Dict[str, str]] = None,
    llm: Optional[BaseLLM] = None,
) -> Callable[[BaseMemory], str]:
    """
    Create a router for plan-and-execute workflows like Cursor.

    Args:
        planner_agent: Name of the agent responsible for creating plans
        executor_agent: Name of the agent responsible for executing steps
        reviewer_agent: Optional name of the agent responsible for reviewing results
        additional_agents: Additional agents that can be used in execution steps
        llm: LLM instance for routing decisions

    Returns:
        Router function for plan-execute workflows
    """
    agents = {
        planner_agent: 'Creates detailed execution plans by breaking down tasks into sequential steps',
        executor_agent: 'Executes individual steps from the execution plan',
    }

    if reviewer_agent:
        agents[reviewer_agent] = 'Reviews and validates completed work'

    if additional_agents:
        agents.update(additional_agents)

    return create_llm_router(
        'plan_execute',
        agents=agents,
        planner_agent=planner_agent,
        executor_agent=executor_agent,
        reviewer_agent=reviewer_agent,
        llm=llm,
    )


# Backward compatibility alias
def create_main_critic_flow_router(
    main_agent: str = 'main_agent',
    critic_agent: str = 'critic',
    final_agent: str = 'final_agent',
    allow_early_exit: bool = False,
    llm: Optional[BaseLLM] = None,
) -> Callable[[BaseMemory], str]:
    """
    DEPRECATED: Use create_main_critic_reflection_router instead.
    Create a router for the A -> B -> A -> C reflection pattern (main -> critic -> main -> final).
    """
    return create_main_critic_reflection_router(
        main_agent=main_agent,
        critic_agent=critic_agent,
        final_agent=final_agent,
        allow_early_exit=allow_early_exit,
        llm=llm,
    )
