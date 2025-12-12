"""
Pydantic models for validating arium YAML configurations.

These models ensure that YAML configurations are properly structured
and validated before being used to create arium workflows.
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict

# Import shared models from agent.py
from flo_ai.models.agent import (
    MetadataModel,
    LLMConfigModel,
    AgentConfigModel,
)


class AriumAgentConfigModel(AgentConfigModel):
    """Agent configuration within an arium workflow.

    Extends AgentConfigModel to support arium-specific configuration methods:
    - Name-only reference to pre-built agent (allowed in arium, not in standalone agent)
    - Inline yaml_config string
    - External yaml_file reference
    """

    yaml_config: Optional[str] = Field(
        None, description='Inline YAML configuration string for agent'
    )
    yaml_file: Optional[str] = Field(
        None, description='Path to YAML file containing agent configuration'
    )

    def model_post_init(self, __context):
        """Validate agent configuration methods for arium context.

        Overrides parent validation to allow name-only references (for pre-built agents)
        and to validate arium-specific configuration methods (yaml_config, yaml_file).
        """
        # Count how many configuration methods are provided
        config_methods = [
            self.job or self.prompt,
            self.yaml_config,
            self.yaml_file,
        ]
        provided_methods = sum(1 for method in config_methods if method is not None)

        # If model is provided, it indicates direct configuration attempt
        # In this case, we need job/prompt (unless using yaml_config/yaml_file)
        if self.model is not None:
            if not self.yaml_config and not self.yaml_file:
                # Model provided but no yaml_config/yaml_file means direct config
                # Must have job or prompt
                if not self.job and not self.prompt:
                    raise ValueError(
                        f"Agent '{self.name}' has 'model' specified but is missing 'job' or 'prompt' field. "
                        "When using direct configuration with a model, 'job' or 'prompt' is required."
                    )

        # If only name is provided (no model, no config methods), it's a reference to a pre-built agent (valid in arium)
        if provided_methods == 0 and self.model is None:
            # This is a reference to a pre-built agent - valid in arium context
            # Skip parent validation which requires job/prompt
            return

        # If multiple methods are provided, that's ambiguous
        if provided_methods > 1:
            methods = []
            if self.job or self.prompt:
                methods.append('job/prompt')
            if self.yaml_config:
                methods.append('yaml_config')
            if self.yaml_file:
                methods.append('yaml_file')
            raise ValueError(
                f"Agent '{self.name}' has multiple configuration methods: {', '.join(methods)}. "
                "Only one method should be provided."
            )

        # If using direct config (job/prompt), ensure at least one is provided
        # This mirrors the parent validation but only when using direct config
        if not self.yaml_config and not self.yaml_file:
            if not self.job and not self.prompt:
                raise ValueError(
                    "Agent configuration must have either 'job' or 'prompt' field when using direct configuration"
                )


class FunctionNodeConfigModel(BaseModel):
    """Function node configuration in arium workflow."""

    name: str = Field(..., description='Function node name')
    function_name: str = Field(..., description='Name of function in function registry')
    description: Optional[str] = Field(None, description='Function description')
    input_filter: Optional[List[str]] = Field(
        None, description='List of input keys to filter'
    )
    prefilled_params: Optional[Dict[str, Any]] = Field(
        None, description='Pre-filled parameters for the function'
    )


class RouterSettingsModel(BaseModel):
    """Settings for router configuration."""

    temperature: Optional[float] = Field(
        None, ge=0.0, le=2.0, description='Temperature setting'
    )
    fallback_strategy: Optional[Literal['first', 'random', 'all']] = Field(
        None, description='Fallback strategy for routing'
    )
    allow_early_exit: Optional[bool] = Field(
        None, description='Allow early exit (for reflection router)'
    )
    planner_agent: Optional[str] = Field(
        None, description='Planner agent name (for plan_execute router)'
    )
    executor_agent: Optional[str] = Field(
        None, description='Executor agent name (for plan_execute router)'
    )
    reviewer_agent: Optional[str] = Field(
        None, description='Reviewer agent name (for plan_execute router)'
    )


class TaskCategoryModel(BaseModel):
    """Task category configuration for task_classifier router."""

    description: str = Field(
        ..., description='Description of what this category handles'
    )
    keywords: Optional[List[str]] = Field(
        None, description='Optional keywords for this category'
    )
    examples: Optional[List[str]] = Field(
        None, description='Optional example tasks for this category'
    )


class RouterConfigModel(BaseModel):
    """Router configuration in arium workflow."""

    name: str = Field(..., description='Router name')
    type: Literal[
        'smart',
        'task_classifier',
        'conversation_analysis',
        'reflection',
        'plan_execute',
    ] = Field(..., description='Router type')
    model: Optional[LLMConfigModel] = Field(
        None, description='LLM model configuration for router'
    )
    settings: Optional[RouterSettingsModel] = Field(None, description='Router settings')
    # Smart router fields
    routing_options: Optional[Dict[str, str]] = Field(
        None, description='Routing options for smart router (agent_name: description)'
    )
    # Task classifier router fields
    task_categories: Optional[Dict[str, TaskCategoryModel]] = Field(
        None, description='Task categories for task_classifier router'
    )
    # Conversation analysis router fields
    routing_logic: Optional[Dict[str, str]] = Field(
        None, description='Routing logic for conversation_analysis router'
    )
    # Reflection router fields
    flow_pattern: Optional[List[str]] = Field(
        None, description='Flow pattern for reflection router (list of agent names)'
    )
    # Plan-execute router fields
    agents: Optional[Dict[str, str]] = Field(
        None, description='Agent descriptions for plan_execute router'
    )

    def model_post_init(self, __context):
        """Validate router type-specific requirements."""
        if self.type == 'smart':
            if not self.routing_options:
                raise ValueError(
                    f"Smart router '{self.name}' must specify 'routing_options'"
                )
        elif self.type == 'task_classifier':
            if not self.task_categories:
                raise ValueError(
                    f"Task classifier router '{self.name}' must specify 'task_categories'"
                )
        elif self.type == 'conversation_analysis':
            if not self.routing_logic:
                raise ValueError(
                    f"Conversation analysis router '{self.name}' must specify 'routing_logic'"
                )
        elif self.type == 'reflection':
            if not self.flow_pattern:
                raise ValueError(
                    f"Reflection router '{self.name}' must specify 'flow_pattern'"
                )
        elif self.type == 'plan_execute':
            if not self.agents:
                raise ValueError(
                    f"Plan-Execute router '{self.name}' must specify 'agents'"
                )


class EdgeConfigModel(BaseModel):
    """Edge configuration in arium workflow."""

    model_config = ConfigDict(populate_by_name=True)  # Allow 'from' alias

    from_: str = Field(..., alias='from', description='Source node name')
    to: List[str] = Field(..., description='Target node names')
    router: Optional[str] = Field(None, description='Router name to use for this edge')


class WorkflowConfigModel(BaseModel):
    """Workflow configuration in arium."""

    start: str = Field(..., description='Start node name')
    edges: List[EdgeConfigModel] = Field(..., description='List of edges')
    end: List[str] = Field(..., description='List of end node names')

    @field_validator('edges', mode='before')
    @classmethod
    def validate_edges(cls, v):
        """Validate edges configuration."""
        if not isinstance(v, list):
            raise ValueError('Edges must be a list')
        return v


class AriumNodeConfigModel(BaseModel):
    """Nested arium node configuration."""

    name: str = Field(..., description='Arium node name')
    inherit_variables: Optional[bool] = Field(
        True, description='Whether to inherit parent variables'
    )
    yaml_file: Optional[str] = Field(
        None, description='Path to YAML file containing nested arium configuration'
    )
    # Inline nested arium configuration
    agents: Optional[List[AriumAgentConfigModel]] = Field(
        None, description='List of agents for nested arium'
    )
    function_nodes: Optional[List[FunctionNodeConfigModel]] = Field(
        None, description='List of function nodes for nested arium'
    )
    routers: Optional[List['RouterConfigModel']] = Field(
        None, description='List of routers for nested arium'
    )
    ariums: Optional[List['AriumNodeConfigModel']] = Field(
        None, description='Nested arium nodes (supports nesting)'
    )
    iterators: Optional[List['ForEachNodeConfigModel']] = Field(
        None, description='List of foreach nodes for nested arium'
    )
    workflow: Optional[WorkflowConfigModel] = Field(
        None, description='Workflow configuration for nested arium'
    )

    def model_post_init(self, __context):
        """Validate that either yaml_file or inline config is provided."""
        has_yaml_file = self.yaml_file is not None
        has_inline_config = (
            self.agents is not None
            or self.function_nodes is not None
            or self.routers is not None
            or self.ariums is not None
            or self.iterators is not None
            or self.workflow is not None
        )

        if not has_yaml_file and not has_inline_config:
            raise ValueError(
                f"Arium node '{self.name}' must have either 'yaml_file' or inline configuration"
            )

        if has_yaml_file and has_inline_config:
            raise ValueError(
                f"Arium node '{self.name}' cannot have both 'yaml_file' and inline configuration"
            )

        if has_inline_config and not self.workflow:
            raise ValueError(
                f"Arium node '{self.name}' with inline configuration must specify 'workflow'"
            )


class ForEachNodeConfigModel(BaseModel):
    """ForEach node configuration in arium workflow."""

    name: str = Field(..., description='ForEach node name')
    execute_node: str = Field(..., description='Name of node to execute on each item')


class AriumConfigModel(BaseModel):
    """Main arium configuration model."""

    agents: Optional[List[AriumAgentConfigModel]] = Field(
        None, description='List of agents in the workflow'
    )
    function_nodes: Optional[List[FunctionNodeConfigModel]] = Field(
        None, description='List of function nodes in the workflow'
    )
    routers: Optional[List[RouterConfigModel]] = Field(
        None, description='List of routers in the workflow'
    )
    ariums: Optional[List[AriumNodeConfigModel]] = Field(
        None, description='List of nested arium nodes'
    )
    iterators: Optional[List[ForEachNodeConfigModel]] = Field(
        None, description="List of foreach nodes (aliased as 'iterators' in YAML)"
    )
    foreach_nodes: Optional[List[ForEachNodeConfigModel]] = Field(
        None, description='List of foreach nodes (alternative name)'
    )
    workflow: WorkflowConfigModel = Field(..., description='Workflow configuration')

    @field_validator('iterators', 'foreach_nodes', mode='before')
    @classmethod
    def validate_foreach_nodes(cls, v):
        """Handle both 'iterators' and 'foreach_nodes' aliases."""
        return v

    def model_post_init(self, __context):
        """Merge iterators and foreach_nodes if both are provided."""
        # Merge iterators and foreach_nodes (they're aliases)
        if self.iterators and self.foreach_nodes:
            # Prefer foreach_nodes if both are provided
            self.iterators = self.foreach_nodes
            self.foreach_nodes = None
        elif self.foreach_nodes:
            self.iterators = self.foreach_nodes
            self.foreach_nodes = None

        # Validate that at least one node type is defined
        has_nodes = (
            (self.agents and len(self.agents) > 0)
            or (self.function_nodes and len(self.function_nodes) > 0)
            or (self.ariums and len(self.ariums) > 0)
            or (self.iterators and len(self.iterators) > 0)
        )

        if not has_nodes:
            raise ValueError(
                'Arium configuration must have at least one of: agents, function_nodes, ariums, or iterators'
            )


class AriumYamlModel(BaseModel):
    """Root model for arium YAML configuration."""

    metadata: Optional[MetadataModel] = Field(None, description='Metadata section')
    arium: AriumConfigModel = Field(..., description='Arium configuration')

    def model_post_init(self, __context):
        """Additional validation if needed."""
        pass


# Update forward references for recursive types
AriumNodeConfigModel.model_rebuild()
RouterConfigModel.model_rebuild()
ForEachNodeConfigModel.model_rebuild()
