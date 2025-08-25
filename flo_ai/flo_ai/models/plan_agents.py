"""
Plan Execution Agents for Flo AI Framework

This module provides standard agent classes for plan-based execution patterns,
making it easy to create plan-and-execute workflows.
"""

from typing import List, Optional
from flo_ai.models.agent import Agent
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.arium.memory import PlanAwareMemory
from flo_ai.tool.plan_tool import PlanTool, StepTool, PlanStatusTool


class PlannerAgent(Agent):
    """
    Agent specialized for creating execution plans.

    Automatically equipped with tools to store plans in PlanAwareMemory.
    """

    def __init__(
        self,
        memory: PlanAwareMemory,
        llm: BaseLLM,
        name: str = 'planner',
        system_prompt: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize the planner agent.

        Args:
            memory: PlanAwareMemory instance to store plans in
            llm: LLM instance for the agent
            name: Agent name (default: "planner")
            system_prompt: Custom system prompt, or uses default if None
            **kwargs: Additional arguments for Agent
        """

        # Default system prompt for planners
        if system_prompt is None:
            system_prompt = """You are a project planner. Create execution plans in this EXACT format:

EXECUTION PLAN: [Clear Title]
DESCRIPTION: [Brief description]

STEPS:
1. step_1: [Description] → [agent_name]
2. step_2: [Description] → [agent_name] (depends on: step_1)
3. step_3: [Description] → [agent_name] (depends on: step_1, step_2)

Rules:
- Use clear, actionable step descriptions
- Assign steps to appropriate agent names
- Include dependencies where steps must be done in sequence
- Keep step IDs simple (step_1, step_2, etc.)

IMPORTANT: After generating the plan text, use the store_execution_plan tool to save it."""

        # Create plan tool
        plan_tool = PlanTool(memory)
        plan_status_tool = PlanStatusTool(memory)

        super().__init__(
            name=name,
            system_prompt=system_prompt,
            llm=llm,
            tools=[plan_tool, plan_status_tool],
            **kwargs,
        )


class ExecutorAgent(Agent):
    """
    Agent specialized for executing plan steps.

    Automatically equipped with tools to mark steps as completed in PlanAwareMemory.
    """

    def __init__(
        self,
        memory: PlanAwareMemory,
        llm: BaseLLM,
        name: str,
        system_prompt: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize the executor agent.

        Args:
            memory: PlanAwareMemory instance to update plans in
            llm: LLM instance for the agent
            name: Agent name (must match agent names used in plans)
            system_prompt: Custom system prompt, or uses default if None
            **kwargs: Additional arguments for Agent
        """

        # Default system prompt for executors
        if system_prompt is None:
            system_prompt = f"""You are a {name} executing specific steps from an execution plan.

Process:
1. Check the current execution plan status using check_plan_status
2. Look for steps assigned to "{name}" that are ready to execute
3. Execute the step and provide detailed results
4. Use complete_step tool to mark the step as completed with your results

Focus on providing high-quality, detailed work for each step you execute."""

        # Create step tools
        step_tool = StepTool(memory, name)
        plan_status_tool = PlanStatusTool(memory)

        super().__init__(
            name=name,
            system_prompt=system_prompt,
            llm=llm,
            tools=[step_tool, plan_status_tool],
            **kwargs,
        )


def create_plan_execution_agents(
    memory: PlanAwareMemory,
    llm: BaseLLM,
    executor_agents: List[str],
    planner_name: str = 'planner',
) -> dict:
    """
    Factory function to create a complete set of plan execution agents.

    Args:
        memory: PlanAwareMemory instance
        llm: LLM instance for all agents
        executor_agents: List of executor agent names (e.g., ["developer", "tester", "reviewer"])
        planner_name: Name for the planner agent

    Returns:
        Dict mapping agent names to agent instances
    """
    agents = {}

    # Create planner
    agents[planner_name] = PlannerAgent(memory=memory, llm=llm, name=planner_name)

    # Create executors
    for agent_name in executor_agents:
        agents[agent_name] = ExecutorAgent(memory=memory, llm=llm, name=agent_name)

    return agents


def create_software_development_agents(memory: PlanAwareMemory, llm: BaseLLM) -> dict:
    """
    Create a standard set of agents for software development workflows.

    Args:
        memory: PlanAwareMemory instance
        llm: LLM instance for all agents

    Returns:
        Dict with planner, developer, tester, and reviewer agents
    """
    agents = {}

    # Planner with software development focus
    agents['planner'] = PlannerAgent(
        memory=memory,
        llm=llm,
        name='planner',
        system_prompt="""You are a software development project planner. Create execution plans for development tasks.

EXECUTION PLAN: [Clear Title]
DESCRIPTION: [Brief description]

STEPS:
1. step_1: [Development task] → developer
2. step_2: [Development task] → developer (depends on: step_1)
3. step_3: [Testing task] → tester (depends on: step_2)
4. step_4: [Review task] → reviewer (depends on: step_3)

Use these agents: developer, tester, reviewer
Focus on breaking down development tasks into logical, sequential steps.

IMPORTANT: After generating the plan, use store_execution_plan to save it.""",
    )

    # Developer
    agents['developer'] = ExecutorAgent(
        memory=memory,
        llm=llm,
        name='developer',
        system_prompt="""You are a software developer executing implementation steps.
Provide detailed code implementations, technical designs, and development work.
Always check the plan status first, then execute your assigned steps thoroughly.""",
    )

    # Tester
    agents['tester'] = ExecutorAgent(
        memory=memory,
        llm=llm,
        name='tester',
        system_prompt="""You are a QA tester validating implementations.
Create comprehensive test scenarios, validate functionality, and report results.
Always check the plan status first, then execute your assigned testing steps.""",
    )

    # Reviewer
    agents['reviewer'] = ExecutorAgent(
        memory=memory,
        llm=llm,
        name='reviewer',
        system_prompt="""You are a code reviewer providing final validation.
Review completed work, check quality, and provide final approval or feedback.
Always check the plan status first, then execute your assigned review steps.""",
    )

    return agents
