from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List, Dict, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

# Define the generic type variable
T = TypeVar('T')


class StepStatus(Enum):
    """Status of a plan step"""

    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    FAILED = 'failed'
    SKIPPED = 'skipped'


@dataclass
class PlanStep:
    """Represents a single step in an execution plan"""

    id: str
    description: str
    agent: str  # Which agent should execute this step
    dependencies: List[str] = field(default_factory=list)  # Step IDs this depends on
    status: StepStatus = StepStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """Represents a complete execution plan"""

    id: str
    title: str
    description: str
    steps: List[PlanStep] = field(default_factory=list)
    created_by: str = 'planner'
    status: str = 'active'  # active, completed, failed, paused
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_next_steps(self) -> List[PlanStep]:
        """Get steps that are ready to execute (pending with no pending dependencies)"""
        next_steps = []
        for step in self.steps:
            if step.status == StepStatus.PENDING:
                # Check if all dependencies are completed
                if all(
                    self.get_step(dep_id).status == StepStatus.COMPLETED
                    for dep_id in step.dependencies
                ):
                    next_steps.append(step)
        return next_steps

    def get_step(self, step_id: str) -> Optional[PlanStep]:
        """Get a step by ID"""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def mark_step_completed(self, step_id: str, result: str = None):
        """Mark a step as completed"""
        step = self.get_step(step_id)
        if step:
            step.status = StepStatus.COMPLETED
            step.result = result

    def mark_step_failed(self, step_id: str, error: str = None):
        """Mark a step as failed"""
        step = self.get_step(step_id)
        if step:
            step.status = StepStatus.FAILED
            step.error = error

    def is_completed(self) -> bool:
        """Check if all steps are completed"""
        return all(step.status == StepStatus.COMPLETED for step in self.steps)

    def has_failed_steps(self) -> bool:
        """Check if any steps have failed"""
        return any(step.status == StepStatus.FAILED for step in self.steps)


class BaseMemory(ABC, Generic[T]):
    @abstractmethod
    def add(self, m: T):
        pass

    @abstractmethod
    def get(self) -> List[T]:
        pass

    # Plan management methods (optional - only implemented by memory classes that support plans)
    def add_plan(self, plan: ExecutionPlan):
        """Add an execution plan (override in subclasses that support plans)"""
        raise NotImplementedError('This memory type does not support plans')

    def get_current_plan(self) -> Optional[ExecutionPlan]:
        """Get the current active plan (override in subclasses that support plans)"""
        return None

    def update_plan(self, plan: ExecutionPlan):
        """Update an existing plan (override in subclasses that support plans)"""
        raise NotImplementedError('This memory type does not support plans')

    def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Get a plan by ID (override in subclasses that support plans)"""
        return None


class MessageMemory(BaseMemory[Dict[str, str]]):
    def __init__(self):
        self.messages = []

    def add(self, message: Dict[str, str]):
        self.messages.append(message)

    def get(self) -> List[Dict[str, str]]:
        return self.messages


class PlanAwareMemory(BaseMemory[Dict[str, str]]):
    """Enhanced memory that supports both messages and execution plans"""

    def __init__(self):
        self.messages = []
        self.plans: Dict[str, ExecutionPlan] = {}
        self.current_plan_id: Optional[str] = None

    def add(self, message: Dict[str, str]):
        """Add a message to memory"""
        self.messages.append(message)

    def get(self) -> List[Dict[str, str]]:
        """Get all messages"""
        return self.messages

    # Plan management methods
    def add_plan(self, plan: ExecutionPlan):
        """Add an execution plan and set it as current"""
        self.plans[plan.id] = plan
        self.current_plan_id = plan.id

    def get_current_plan(self) -> Optional[ExecutionPlan]:
        """Get the current active plan"""
        if self.current_plan_id and self.current_plan_id in self.plans:
            return self.plans[self.current_plan_id]
        return None

    def update_plan(self, plan: ExecutionPlan):
        """Update an existing plan"""
        if plan.id in self.plans:
            self.plans[plan.id] = plan
        else:
            raise ValueError(f'Plan {plan.id} not found in memory')

    def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Get a plan by ID"""
        return self.plans.get(plan_id)

    def set_current_plan(self, plan_id: str):
        """Set the current active plan"""
        if plan_id in self.plans:
            self.current_plan_id = plan_id
        else:
            raise ValueError(f'Plan {plan_id} not found in memory')

    def get_all_plans(self) -> List[ExecutionPlan]:
        """Get all plans"""
        return list(self.plans.values())

    def remove_plan(self, plan_id: str):
        """Remove a plan from memory"""
        if plan_id in self.plans:
            del self.plans[plan_id]
            if self.current_plan_id == plan_id:
                self.current_plan_id = None
