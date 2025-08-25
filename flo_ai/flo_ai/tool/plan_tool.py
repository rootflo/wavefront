"""
Plan Execution Tools for Flo AI Framework

This module provides reusable tools for plan-based execution patterns,
enabling agents to create, store, and manage execution plans automatically.
"""

import uuid
import re
from flo_ai.tool.base_tool import Tool
from flo_ai.arium.memory import PlanAwareMemory, ExecutionPlan, PlanStep, StepStatus


class PlanTool(Tool):
    """Tool for creating and storing execution plans in PlanAwareMemory"""

    def __init__(self, memory: PlanAwareMemory):
        """
        Initialize the plan tool.

        Args:
            memory: PlanAwareMemory instance to store plans in
        """
        self.memory = memory
        super().__init__(
            name='store_execution_plan',
            description='Create and store an execution plan from plan text. Use this after generating a plan.',
            function=self._execute_plan_storage,
            parameters={
                'plan_text': {
                    'type': 'string',
                    'description': 'The generated plan text in the required format',
                }
            },
        )

    async def _execute_plan_storage(self, plan_text: str) -> str:
        """Parse plan text and store ExecutionPlan object in memory"""
        try:
            execution_plan = self._parse_plan_text(plan_text)

            if execution_plan:
                self.memory.add_plan(execution_plan)

                plan_summary = f'✅ Plan stored: {execution_plan.title}\n'
                plan_summary += f'📊 Steps: {len(execution_plan.steps)}\n'

                for i, step in enumerate(execution_plan.steps, 1):
                    deps = (
                        f" (depends: {', '.join(step.dependencies)})"
                        if step.dependencies
                        else ''
                    )
                    plan_summary += (
                        f'  {i}. {step.id}: {step.description} → {step.agent}{deps}\n'
                    )

                return plan_summary
            else:
                return '❌ Failed to parse plan text into ExecutionPlan'

        except Exception as e:
            return f'❌ Error storing plan: {str(e)}'

    def _parse_plan_text(self, plan_text: str) -> ExecutionPlan:
        """Parse LLM-generated plan text into ExecutionPlan object"""

        # Extract title
        title_match = re.search(r'EXECUTION PLAN:\s*(.+)', plan_text)
        title = title_match.group(1).strip() if title_match else 'Generated Plan'

        # Extract description
        desc_match = re.search(r'DESCRIPTION:\s*(.+)', plan_text)
        description = desc_match.group(1).strip() if desc_match else 'Execution plan'

        # Extract steps using regex
        steps = []
        step_pattern = (
            r'(\d+)\.\s*(\w+):\s*(.+?)\s*→\s*(\w+)(?:\s*\(depends on:\s*([^)]+)\))?'
        )

        for match in re.finditer(step_pattern, plan_text, re.MULTILINE):
            step_num, step_id, step_desc, agent, deps_str = match.groups()

            dependencies = []
            if deps_str:
                dependencies = [dep.strip() for dep in deps_str.split(',')]

            step = PlanStep(
                id=step_id,
                description=step_desc.strip(),
                agent=agent,
                dependencies=dependencies,
                status=StepStatus.PENDING,
            )
            steps.append(step)

        return ExecutionPlan(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            steps=steps,
            created_by='planner',
        )


class StepTool(Tool):
    """Tool for marking execution steps as completed"""

    def __init__(self, memory: PlanAwareMemory, agent_name: str):
        """
        Initialize the step tool.

        Args:
            memory: PlanAwareMemory instance to update plans in
            agent_name: Name of the agent this tool belongs to
        """
        self.memory = memory
        self.agent_name = agent_name
        super().__init__(
            name='complete_step',
            description='Mark a plan step as completed after executing it',
            function=self._execute_step_completion,
            parameters={
                'step_id': {
                    'type': 'string',
                    'description': 'The ID of the step that was completed',
                },
                'result': {
                    'type': 'string',
                    'description': 'The result or output of completing the step',
                },
            },
        )

    async def _execute_step_completion(self, step_id: str, result: str) -> str:
        """Mark a step as completed and store the result"""
        try:
            current_plan = self.memory.get_current_plan()
            if not current_plan:
                return '❌ No current plan found'

            step = current_plan.get_step(step_id)
            if not step:
                return f'❌ Step {step_id} not found in current plan'

            if step.agent != self.agent_name:
                return f'❌ Step {step_id} is assigned to {step.agent}, not {self.agent_name}'

            # Mark step as completed
            step.status = StepStatus.COMPLETED
            step.result = result
            self.memory.update_plan(current_plan)

            return f'✅ Step {step_id} marked as completed'

        except Exception as e:
            return f'❌ Error completing step: {str(e)}'


class PlanStatusTool(Tool):
    """Tool for checking the current plan status and next steps"""

    def __init__(self, memory: PlanAwareMemory):
        """
        Initialize the plan status tool.

        Args:
            memory: PlanAwareMemory instance to check
        """
        self.memory = memory
        super().__init__(
            name='check_plan_status',
            description='Check the current execution plan status and get next available steps',
            function=self._execute_status_check,
            parameters={},
        )

    async def _execute_status_check(self) -> str:
        """Get current plan status and next steps"""
        try:
            current_plan = self.memory.get_current_plan()
            if not current_plan:
                return '❌ No current execution plan found'

            # Get plan overview
            status_info = f'📋 Current Plan: {current_plan.title}\n'
            status_info += f'📝 Description: {current_plan.description}\n'
            status_info += f'✅ Completed: {current_plan.is_completed()}\n'

            # Get next steps
            next_steps = current_plan.get_next_steps()
            if next_steps:
                status_info += f'\n🎯 Next Steps ({len(next_steps)} available):\n'
                for step in next_steps:
                    deps = (
                        f" (depends: {', '.join(step.dependencies)})"
                        if step.dependencies
                        else ''
                    )
                    status_info += (
                        f'  • {step.id}: {step.description} → {step.agent}{deps}\n'
                    )
            else:
                if current_plan.is_completed():
                    status_info += '\n🎉 All steps completed!'
                else:
                    status_info += '\n⏳ Waiting for dependencies to complete'

            # Show all steps with status
            status_info += '\n📊 All Steps:\n'
            for step in current_plan.steps:
                status_icon = {
                    StepStatus.PENDING: '○',
                    StepStatus.IN_PROGRESS: '⏳',
                    StepStatus.COMPLETED: '✅',
                    StepStatus.FAILED: '❌',
                }.get(step.status, '○')
                status_info += (
                    f'  {status_icon} {step.id}: {step.description} → {step.agent}\n'
                )

            return status_info

        except Exception as e:
            return f'❌ Error checking plan status: {str(e)}'
