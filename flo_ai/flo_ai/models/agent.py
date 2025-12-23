"""
Pydantic models for validating agent YAML configurations.

These models ensure that YAML configurations are properly structured
and validated before being used to create agents.
"""

from typing import List, Optional, Dict, Any, Union, Literal
from pydantic import BaseModel, Field, field_validator

from flo_ai.models import MessageType


class MetadataModel(BaseModel):
    """Metadata section for agent YAML configuration."""

    name: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    tags: Optional[List[str]] = None


class LiteralValueModel(BaseModel):
    """A single value in a literal type field."""

    value: str = Field(..., description='The literal value')
    description: str = Field(..., description='Description of this value')
    examples: Optional[List[str]] = Field(
        None, description='Example strings for this value'
    )


class ParserFieldModel(BaseModel):
    """A field definition in a parser configuration."""

    name: str = Field(..., description='Field name')
    type: Literal['str', 'int', 'bool', 'float', 'literal', 'object', 'array'] = Field(
        ..., description='Field type'
    )
    description: str = Field(..., description='Field description')
    required: Optional[bool] = Field(None, description='Whether field is required')
    values: Optional[List[LiteralValueModel]] = Field(
        None, description='Values for literal type fields'
    )
    items: Optional['ParserFieldModel'] = Field(
        None, description='Item type for array fields'
    )
    fields: Optional[List['ParserFieldModel']] = Field(
        None, description='Nested fields for object type fields'
    )
    default_value_prompt: Optional[str] = Field(
        None, description='Default value prompt for literal fields'
    )

    def model_post_init(self, __context):
        """Validate that literal type fields have values."""
        if self.type == 'literal' and not self.values:
            raise ValueError(
                f"Field '{self.name}' of type 'literal' must specify 'values'."
            )
        if self.type == 'array' and not self.items:
            raise ValueError(
                f"Field '{self.name}' of type 'array' must specify 'items'."
            )
        if self.type == 'object' and not self.fields:
            raise ValueError(
                f"Field '{self.name}' of type 'object' must specify 'fields'."
            )


class ParserModel(BaseModel):
    """Parser configuration for structured output."""

    name: str = Field(..., description='Parser name')
    version: Optional[str] = Field(None, description='Parser version')
    description: Optional[str] = Field(None, description='Parser description')
    fields: List[ParserFieldModel] = Field(..., description='Parser field definitions')


class ExampleModel(BaseModel):
    """Example input/output pair for the agent."""

    input: str = Field(..., description='Example input')
    output: Union[Dict[str, Any], str] = Field(..., description='Example output')


class LLMConfigModel(BaseModel):
    """LLM model configuration."""

    provider: Literal[
        'openai',
        'anthropic',
        'claude',  # Alias for anthropic
        'gemini',
        'google',  # Alias for gemini
        'ollama',
        'vertexai',
        'rootflo',
        'openai_vllm',
    ] = Field(..., description='LLM provider')
    name: Optional[str] = Field(
        None, description='Model name (required for most providers)'
    )
    base_url: Optional[str] = Field(None, description='Custom base URL')
    temperature: Optional[float] = Field(
        None, ge=0.0, le=2.0, description='Temperature setting'
    )
    max_tokens: Optional[int] = Field(None, gt=0, description='Maximum tokens')
    timeout: Optional[int] = Field(None, gt=0, description='Request timeout in seconds')
    # VertexAI specific
    project: Optional[str] = Field(None, description='GCP project ID (for VertexAI)')
    location: Optional[str] = Field(None, description='GCP location (for VertexAI)')
    # RootFlo specific
    model_id: Optional[str] = Field(None, description='Model ID (for RootFlo)')
    # OpenAI vLLM specific
    api_key: Optional[str] = Field(None, description='API key (for openai_vllm)')

    def model_post_init(self, __context):
        """Validate provider-specific requirements."""
        provider = self.provider.lower()

        # Most providers require 'name'
        if provider in ['openai', 'anthropic', 'claude', 'gemini', 'google', 'ollama']:
            if not self.name:
                raise ValueError(
                    f'{provider.title()} provider requires "name" parameter in model configuration'
                )

        # VertexAI requires name, project, and base_url
        if provider == 'vertexai':
            if not self.name:
                raise ValueError('VertexAI provider requires "name" parameter')
            if not self.project:
                raise ValueError('VertexAI provider requires "project" parameter')
            if not self.base_url:
                raise ValueError('VertexAI provider requires "base_url" parameter')

        # RootFlo requires model_id
        if provider == 'rootflo':
            if not self.model_id:
                raise ValueError(
                    'RootFlo provider requires "model_id" in model configuration'
                )

        # OpenAI vLLM requires name, base_url, and api_key
        if provider == 'openai_vllm':
            if not self.name:
                raise ValueError('openai_vllm provider requires "name" parameter')
            if not self.base_url:
                raise ValueError('openai_vllm provider requires "base_url" parameter')
            if not self.api_key:
                raise ValueError('openai_vllm provider requires "api_key" parameter')


class SettingsModel(BaseModel):
    """Agent settings configuration."""

    temperature: Optional[float] = Field(
        None, ge=0.0, le=2.0, description='Temperature setting'
    )
    max_retries: Optional[int] = Field(
        None, ge=0, description='Maximum number of retries'
    )
    reasoning_pattern: Optional[Literal['DIRECT', 'REACT', 'COT']] = Field(
        None, description='Reasoning pattern'
    )


class ToolConfigModel(BaseModel):
    """Tool configuration in YAML."""

    name: str = Field(..., description='Tool name (must exist in tool registry)')
    prefilled_params: Optional[Dict[str, Any]] = Field(
        None, description='Pre-filled parameters for the tool'
    )
    name_override: Optional[str] = Field(
        None, description='Custom name override for the tool'
    )
    description_override: Optional[str] = Field(
        None, description='Custom description override for the tool'
    )


class AgentConfigModel(BaseModel):
    """Main agent configuration model."""

    name: str = Field(..., description='Agent name')
    job: Optional[str] = Field(None, description='System prompt/job description')
    prompt: Optional[str] = Field(None, description='System prompt (alias for job)')
    role: Optional[str] = Field(None, description='Agent role')
    act_as: Optional[str] = Field(
        MessageType.ASSISTANT, description='Agent act_as setting'
    )
    model: Optional[LLMConfigModel] = Field(None, description='LLM model configuration')
    base_url: Optional[str] = Field(
        None, description='Base URL (can be at agent or model level)'
    )
    settings: Optional[SettingsModel] = Field(None, description='Agent settings')
    tools: Optional[List[Union[str, ToolConfigModel]]] = Field(
        None, description='List of tools (strings or tool configs)'
    )
    parser: Optional[ParserModel] = Field(
        None, description='Parser configuration for structured output'
    )
    examples: Optional[List[ExampleModel]] = Field(
        None, description='Example input/output pairs'
    )

    def model_post_init(self, __context):
        """Ensure either job or prompt is provided."""
        if not self.job and not self.prompt:
            raise ValueError(
                "Agent configuration must have either 'job' or 'prompt' field"
            )
        # If both are provided, prefer 'job' and ignore 'prompt'
        if self.job and self.prompt:
            # Keep job, prompt will be ignored in favor of job
            pass

    @field_validator('tools', mode='before')
    @classmethod
    def validate_tools(cls, v):
        """Validate tools configuration."""
        if v is None:
            return v

        # Normalize singletons (common YAML mistake) or fail fast with a clear error
        if isinstance(v, (str, dict, ToolConfigModel)):
            v = [v]
        if not isinstance(v, list):
            raise ValueError(
                'Tools must be a list of tool names or tool config objects'
            )

        for tool in v:
            if isinstance(tool, str):
                # String reference - valid
                continue
            elif isinstance(tool, dict):
                # Should be validated as ToolConfigModel
                if 'name' not in tool:
                    raise ValueError("Tool configuration must have a 'name' field")
            elif isinstance(tool, ToolConfigModel):
                # Already validated as ToolConfigModel - valid
                continue
            else:
                raise ValueError(
                    f'Invalid tool configuration type: {type(tool)}. '
                    "Must be string or dict with 'name' field."
                )
        return v


class AgentYamlModel(BaseModel):
    """Root model for agent YAML configuration."""

    metadata: Optional[MetadataModel] = Field(None, description='Metadata section')
    agent: AgentConfigModel = Field(..., description='Agent configuration')

    def model_post_init(self, __context):
        """Validate that agent has model config or will receive base_llm."""
        # This validation is handled in the builder, but we can note it here
        # The actual check happens in from_yaml when base_llm is None
        pass


# Update forward references for recursive types
ParserFieldModel.model_rebuild()
