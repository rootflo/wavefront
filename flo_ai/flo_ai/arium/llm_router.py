"""
LLM-Powered Router Functions for Arium Workflows

This module provides intelligent routing capabilities using Large Language Models
to make dynamic routing decisions based on conversation context and history.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Callable, Any, Union, get_args
from functools import wraps
from flo_ai.arium.memory import BaseMemory
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

        # Format conversation history
        if isinstance(conversation, list):
            conversation_text = '\n'.join(
                [str(msg) for msg in conversation[-5:]]
            )  # Last 5 messages
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
        router_type: Type of router ("smart", "task_classifier", "conversation_analysis")
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
