"""
Plan state and the ``update_plan`` tool behind ``ReasoningPattern.PLAN_EXECUTE``.

The plan belongs to one agent and lives for one ``run``. The model writes it
by calling ``update_plan`` with the whole step list each time, so there is no
plan text to parse and no step ids to keep in sync.
"""

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, List

from flo_ai.tool.base_tool import Tool

PLAN_TOOL_NAME = 'update_plan'


class PlanStepStatus(str, Enum):
    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    SKIPPED = 'skipped'


_FINISHED = (PlanStepStatus.COMPLETED, PlanStepStatus.SKIPPED)

_STATUS_ICONS = {
    PlanStepStatus.PENDING: '[ ]',
    PlanStepStatus.IN_PROGRESS: '[~]',
    PlanStepStatus.COMPLETED: '[x]',
    PlanStepStatus.SKIPPED: '[-]',
}


@dataclass
class PlanStep:
    description: str
    status: PlanStepStatus = PlanStepStatus.PENDING


class Plan:
    """An ordered list of steps an agent is working through."""

    def __init__(self) -> None:
        self.steps: List[PlanStep] = []

    def reset(self) -> None:
        self.steps = []

    def update(self, steps: Any) -> None:
        """Replace the plan with ``steps``.

        Raises:
            ValueError: If ``steps`` is not a non-empty list of valid steps.
                The plan is left unchanged.
        """
        # Some providers hand array arguments over as a JSON string.
        if isinstance(steps, str):
            try:
                steps = json.loads(steps)
            except json.JSONDecodeError as e:
                raise ValueError(f'steps is not valid JSON: {e}') from e

        if not isinstance(steps, list) or not steps:
            raise ValueError('steps must be a non-empty list')

        parsed: List[PlanStep] = []
        for index, raw in enumerate(steps, 1):
            if isinstance(raw, str):
                raw = {'description': raw}
            if not isinstance(raw, dict):
                raise ValueError(f'step {index} must be an object')

            description = str(raw.get('description') or '').strip()
            if not description:
                raise ValueError(f'step {index} has no description')

            status = raw.get('status') or PlanStepStatus.PENDING.value
            try:
                parsed.append(PlanStep(description, PlanStepStatus(status)))
            except ValueError:
                allowed = ', '.join(s.value for s in PlanStepStatus)
                raise ValueError(
                    f"step {index} has unknown status '{status}' (use one of: {allowed})"
                ) from None

        self.steps = parsed

    def unfinished(self) -> List[PlanStep]:
        return [step for step in self.steps if step.status not in _FINISHED]

    def is_complete(self) -> bool:
        """True when a plan exists and every step is completed or skipped."""
        return bool(self.steps) and not self.unfinished()

    def render(self) -> str:
        if not self.steps:
            return 'No plan yet.'
        return '\n'.join(
            f'{index}. {_STATUS_ICONS[step.status]} {step.description}'
            for index, step in enumerate(self.steps, 1)
        )


def create_plan_tool(plan: Plan) -> Tool:
    """Create the ``update_plan`` tool that writes to ``plan``."""

    async def _update_plan(steps: Any) -> str:
        # A malformed plan is the model's mistake to correct, so it gets the
        # reason back as a tool result instead of failing the agent's run.
        try:
            plan.update(steps)
        except ValueError as e:
            return f'Plan not updated: {e}'

        remaining = len(plan.unfinished())
        summary = (
            'All steps are finished. Give your final answer.'
            if remaining == 0
            else f'{remaining} step(s) left.'
        )
        return f'Plan updated:\n{plan.render()}\n{summary}'

    return Tool(
        name=PLAN_TOOL_NAME,
        description=(
            'Create or update your plan. Always send the complete list of steps '
            'with their current status; it replaces the previous plan.'
        ),
        function=_update_plan,
        parameters={
            'steps': {
                'type': 'array',
                'description': 'Every step of the plan, in order',
                'items': {
                    'type': 'object',
                    'properties': {
                        'description': {
                            'type': 'string',
                            'description': 'What this step does',
                        },
                        'status': {
                            'type': 'string',
                            'enum': [s.value for s in PlanStepStatus],
                        },
                    },
                    'required': ['description', 'status'],
                },
            }
        },
    )
