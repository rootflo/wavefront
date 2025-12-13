"""
Tests for agent YAML validation using Pydantic models.

This module tests all validation rules defined in flo_ai.models.agent,
ensuring that YAML configurations are properly validated before being used.
"""

import pytest
import yaml
from pydantic import ValidationError

from typing import cast

from flo_ai.models.agent import (
    AgentYamlModel,
    AgentConfigModel,
    LiteralValueModel,
    MetadataModel,
    LLMConfigModel,
    SettingsModel,
    ParserModel,
    ParserFieldModel,
    ExampleModel,
    ToolConfigModel,
)


class TestMetadataModel:
    """Test cases for MetadataModel validation."""

    def test_valid_metadata(self):
        """Test valid metadata configuration."""
        metadata = MetadataModel(
            name='test-agent',
            version='1.0.0',
            description='A test agent',
            author='Test Author',
            tags=['test', 'agent'],
        )
        assert metadata.name == 'test-agent'
        assert metadata.version == '1.0.0'
        assert metadata.description == 'A test agent'
        assert metadata.author == 'Test Author'
        assert metadata.tags == ['test', 'agent']

    def test_empty_metadata(self):
        """Test that all metadata fields are optional."""
        metadata = MetadataModel()
        assert metadata.name is None
        assert metadata.version is None
        assert metadata.description is None
        assert metadata.author is None
        assert metadata.tags is None

    def test_partial_metadata(self):
        """Test metadata with only some fields."""
        metadata = MetadataModel(name='test-agent', version='1.0.0')
        assert metadata.name == 'test-agent'
        assert metadata.version == '1.0.0'
        assert metadata.description is None


class TestParserFieldModel:
    """Test cases for ParserFieldModel validation."""

    def test_valid_string_field(self):
        """Test valid string field."""
        field = ParserFieldModel(
            name='query',
            type='str',
            description='A query string',
            required=True,
        )
        assert field.name == 'query'
        assert field.type == 'str'
        assert field.description == 'A query string'
        assert field.required is True

    def test_valid_literal_field(self):
        """Test valid literal field with values."""
        field = ParserFieldModel(
            name='status',
            type='literal',
            description='Status value',
            values=[
                LiteralValueModel(value='active', description='Active status'),
                LiteralValueModel(value='inactive', description='Inactive status'),
            ],
        )
        assert field.type == 'literal'
        assert field.values is not None
        assert len(field.values) == 2
        assert field.values[0].value == 'active'

    def test_literal_field_missing_values(self):
        """Test that literal fields must have values."""
        with pytest.raises(ValueError, match="must specify 'values'"):
            ParserFieldModel(
                name='status',
                type='literal',
                description='Status value',
            )

    def test_valid_array_field(self):
        """Test valid array field with items."""
        field = ParserFieldModel(
            name='items',
            type='array',
            description='List of items',
            items=ParserFieldModel(
                name='item',
                type='str',
                description='An item',
            ),
        )
        assert field.type == 'array'
        assert field.items is not None
        assert field.items.type == 'str'

    def test_array_field_missing_items(self):
        """Test that array fields must have items."""
        with pytest.raises(ValueError, match="must specify 'items'"):
            ParserFieldModel(
                name='items',
                type='array',
                description='List of items',
            )

    def test_valid_object_field(self):
        """Test valid object field with nested fields."""
        field = ParserFieldModel(
            name='user',
            type='object',
            description='User object',
            fields=[
                ParserFieldModel(
                    name='name',
                    type='str',
                    description='User name',
                ),
                ParserFieldModel(
                    name='age',
                    type='int',
                    description='User age',
                ),
            ],
        )
        assert field.type == 'object'
        assert field.fields is not None
        assert len(field.fields) == 2

    def test_object_field_missing_fields(self):
        """Test that object fields must have fields."""
        with pytest.raises(ValueError, match="must specify 'fields'"):
            ParserFieldModel(
                name='user',
                type='object',
                description='User object',
            )

    def test_nested_object_field(self):
        """Test nested object fields."""
        field = ParserFieldModel(
            name='address',
            type='object',
            description='Address object',
            fields=[
                ParserFieldModel(
                    name='street',
                    type='str',
                    description='Street name',
                ),
                ParserFieldModel(
                    name='city',
                    type='object',
                    description='City object',
                    fields=[
                        ParserFieldModel(
                            name='name',
                            type='str',
                            description='City name',
                        ),
                    ],
                ),
            ],
        )
        assert field.type == 'object'
        assert field.fields is not None
        assert field.fields[1].type == 'object'
        assert field.fields[1].fields is not None
        assert field.fields[1].fields[0].type == 'str'


class TestParserModel:
    """Test cases for ParserModel validation."""

    def test_valid_parser(self):
        """Test valid parser configuration."""
        parser = ParserModel(
            name='test_parser',
            version='1.0.0',
            description='A test parser',
            fields=[
                ParserFieldModel(
                    name='query',
                    type='str',
                    description='Query string',
                ),
            ],
        )
        assert parser.name == 'test_parser'
        assert parser.version == '1.0.0'
        assert len(parser.fields) == 1

    def test_parser_missing_required_fields(self):
        """Test that parser must have name and fields."""
        with pytest.raises(ValidationError):
            ParserModel(
                name='test_parser',
                # Missing fields
            )

    def test_parser_optional_fields(self):
        """Test parser with only required fields."""
        parser = ParserModel(
            name='test_parser',
            fields=[
                ParserFieldModel(
                    name='query',
                    type='str',
                    description='Query string',
                ),
            ],
        )
        assert parser.name == 'test_parser'
        assert parser.version is None
        assert parser.description is None


class TestExampleModel:
    """Test cases for ExampleModel validation."""

    def test_valid_example_with_string_output(self):
        """Test valid example with string output."""
        example = ExampleModel(
            input='Hello',
            output='Hi there!',
        )
        assert example.input == 'Hello'
        assert example.output == 'Hi there!'

    def test_valid_example_with_dict_output(self):
        """Test valid example with dictionary output."""
        example = ExampleModel(
            input='Get user info',
            output={'name': 'John', 'age': 30},
        )
        assert example.input == 'Get user info'
        assert example.output == {'name': 'John', 'age': 30}

    def test_example_missing_input(self):
        """Test that example must have input."""
        with pytest.raises(ValidationError):
            ExampleModel(output='Hi there!')

    def test_example_missing_output(self):
        """Test that example must have output."""
        with pytest.raises(ValidationError):
            ExampleModel(input='Hello')


class TestLLMConfigModel:
    """Test cases for LLMConfigModel validation."""

    def test_valid_openai_config(self):
        """Test valid OpenAI model configuration."""
        config = LLMConfigModel(
            provider='openai',
            name='gpt-4',
            temperature=0.7,
            max_tokens=1000,
        )
        assert config.provider == 'openai'
        assert config.name == 'gpt-4'
        assert config.temperature == 0.7
        assert config.max_tokens == 1000

    def test_openai_missing_name(self):
        """Test that OpenAI requires name."""
        with pytest.raises(ValueError, match='requires "name" parameter'):
            LLMConfigModel(provider='openai')

    def test_valid_anthropic_config(self):
        """Test valid Anthropic model configuration."""
        config = LLMConfigModel(
            provider='anthropic',
            name='claude-3-opus-20240229',
            temperature=0.5,
        )
        assert config.provider == 'anthropic'
        assert config.name == 'claude-3-opus-20240229'

    def test_anthropic_missing_name(self):
        """Test that Anthropic requires name."""
        with pytest.raises(ValueError, match='requires "name" parameter'):
            LLMConfigModel(provider='anthropic')

    def test_valid_claude_alias(self):
        """Test that 'claude' alias works for Anthropic."""
        config = LLMConfigModel(
            provider='claude',
            name='claude-3-opus-20240229',
        )
        assert config.provider == 'claude'

    def test_valid_gemini_config(self):
        """Test valid Gemini model configuration."""
        config = LLMConfigModel(
            provider='gemini',
            name='gemini-pro',
            temperature=0.8,
        )
        assert config.provider == 'gemini'
        assert config.name == 'gemini-pro'

    def test_gemini_missing_name(self):
        """Test that Gemini requires name."""
        with pytest.raises(ValueError, match='requires "name" parameter'):
            LLMConfigModel(provider='gemini')

    def test_valid_google_alias(self):
        """Test that 'google' alias works for Gemini."""
        config = LLMConfigModel(
            provider='google',
            name='gemini-pro',
        )
        assert config.provider == 'google'

    def test_valid_ollama_config(self):
        """Test valid Ollama model configuration."""
        config = LLMConfigModel(
            provider='ollama',
            name='llama2',
            base_url='http://localhost:11434',
        )
        assert config.provider == 'ollama'
        assert config.name == 'llama2'

    def test_ollama_missing_name(self):
        """Test that Ollama requires name."""
        with pytest.raises(ValueError, match='requires "name" parameter'):
            LLMConfigModel(provider='ollama')

    def test_valid_vertexai_config(self):
        """Test valid VertexAI model configuration."""
        config = LLMConfigModel(
            provider='vertexai',
            name='gemini-pro',
            project='my-project',
            base_url='https://us-central1-aiplatform.googleapis.com',
            location='us-central1',
        )
        assert config.provider == 'vertexai'
        assert config.project == 'my-project'
        assert config.base_url == 'https://us-central1-aiplatform.googleapis.com'

    def test_vertexai_missing_name(self):
        """Test that VertexAI requires name."""
        with pytest.raises(ValueError, match='requires "name" parameter'):
            LLMConfigModel(
                provider='vertexai',
                project='my-project',
                base_url='https://us-central1-aiplatform.googleapis.com',
            )

    def test_vertexai_missing_project(self):
        """Test that VertexAI requires project."""
        with pytest.raises(ValueError, match='requires "project" parameter'):
            LLMConfigModel(
                provider='vertexai',
                name='gemini-pro',
                base_url='https://us-central1-aiplatform.googleapis.com',
            )

    def test_vertexai_missing_base_url(self):
        """Test that VertexAI requires base_url."""
        with pytest.raises(ValueError, match='requires "base_url" parameter'):
            LLMConfigModel(
                provider='vertexai',
                name='gemini-pro',
                project='my-project',
            )

    def test_valid_rootflo_config(self):
        """Test valid RootFlo model configuration."""
        config = LLMConfigModel(
            provider='rootflo',
            model_id='model-123',
        )
        assert config.provider == 'rootflo'
        assert config.model_id == 'model-123'

    def test_rootflo_missing_model_id(self):
        """Test that RootFlo requires model_id."""
        with pytest.raises(ValueError, match='requires "model_id"'):
            LLMConfigModel(provider='rootflo')

    def test_valid_openai_vllm_config(self):
        """Test valid OpenAI vLLM model configuration."""
        config = LLMConfigModel(
            provider='openai_vllm',
            name='gpt-4',
            base_url='http://localhost:8000/v1',
            api_key='sk-test',
        )
        assert config.provider == 'openai_vllm'
        assert config.name == 'gpt-4'
        assert config.base_url == 'http://localhost:8000/v1'
        assert config.api_key == 'sk-test'

    def test_openai_vllm_missing_name(self):
        """Test that OpenAI vLLM requires name."""
        with pytest.raises(ValueError, match='requires "name" parameter'):
            LLMConfigModel(
                provider='openai_vllm',
                base_url='http://localhost:8000/v1',
                api_key='sk-test',
            )

    def test_openai_vllm_missing_base_url(self):
        """Test that OpenAI vLLM requires base_url."""
        with pytest.raises(ValueError, match='requires "base_url" parameter'):
            LLMConfigModel(
                provider='openai_vllm',
                name='gpt-4',
                api_key='sk-test',
            )

    def test_openai_vllm_missing_api_key(self):
        """Test that OpenAI vLLM requires api_key."""
        with pytest.raises(ValueError, match='requires "api_key" parameter'):
            LLMConfigModel(
                provider='openai_vllm',
                name='gpt-4',
                base_url='http://localhost:8000/v1',
            )

    def test_temperature_range_validation(self):
        """Test temperature range validation (0.0 to 2.0)."""
        # Valid temperatures
        config1 = LLMConfigModel(provider='openai', name='gpt-4', temperature=0.0)
        assert config1.temperature == 0.0

        config2 = LLMConfigModel(provider='openai', name='gpt-4', temperature=2.0)
        assert config2.temperature == 2.0

        # Invalid temperatures
        with pytest.raises(ValidationError):
            LLMConfigModel(provider='openai', name='gpt-4', temperature=-0.1)

        with pytest.raises(ValidationError):
            LLMConfigModel(provider='openai', name='gpt-4', temperature=2.1)

    def test_max_tokens_validation(self):
        """Test max_tokens must be greater than 0."""
        config = LLMConfigModel(provider='openai', name='gpt-4', max_tokens=100)
        assert config.max_tokens == 100

        with pytest.raises(ValidationError):
            LLMConfigModel(provider='openai', name='gpt-4', max_tokens=0)

        with pytest.raises(ValidationError):
            LLMConfigModel(provider='openai', name='gpt-4', max_tokens=-1)

    def test_timeout_validation(self):
        """Test timeout must be greater than 0."""
        config = LLMConfigModel(provider='openai', name='gpt-4', timeout=30)
        assert config.timeout == 30

        with pytest.raises(ValidationError):
            LLMConfigModel(provider='openai', name='gpt-4', timeout=0)

        with pytest.raises(ValidationError):
            LLMConfigModel(provider='openai', name='gpt-4', timeout=-1)


class TestSettingsModel:
    """Test cases for SettingsModel validation."""

    def test_valid_settings(self):
        """Test valid settings configuration."""
        settings = SettingsModel(
            temperature=0.7,
            max_retries=3,
            reasoning_pattern='REACT',
        )
        assert settings.temperature == 0.7
        assert settings.max_retries == 3
        assert settings.reasoning_pattern == 'REACT'

    def test_empty_settings(self):
        """Test that all settings fields are optional."""
        settings = SettingsModel()
        assert settings.temperature is None
        assert settings.max_retries is None
        assert settings.reasoning_pattern is None

    def test_temperature_range_validation(self):
        """Test temperature range validation (0.0 to 2.0)."""
        settings1 = SettingsModel(temperature=0.0)
        assert settings1.temperature == 0.0

        settings2 = SettingsModel(temperature=2.0)
        assert settings2.temperature == 2.0

        with pytest.raises(ValidationError):
            SettingsModel(temperature=-0.1)

        with pytest.raises(ValidationError):
            SettingsModel(temperature=2.1)

    def test_max_retries_validation(self):
        """Test max_retries must be >= 0."""
        settings = SettingsModel(max_retries=0)
        assert settings.max_retries == 0

        settings = SettingsModel(max_retries=5)
        assert settings.max_retries == 5

        with pytest.raises(ValidationError):
            SettingsModel(max_retries=-1)

    def test_reasoning_pattern_validation(self):
        """Test reasoning_pattern must be one of the allowed values."""
        from typing import Literal

        for pattern in ['DIRECT', 'REACT', 'COT']:
            settings = SettingsModel(
                reasoning_pattern=cast(Literal['DIRECT', 'REACT', 'COT'], pattern)
            )
            assert settings.reasoning_pattern == pattern

        with pytest.raises(ValidationError):
            SettingsModel(reasoning_pattern='INVALID')  # type: ignore[arg-type]


class TestToolConfigModel:
    """Test cases for ToolConfigModel validation."""

    def test_valid_tool_config(self):
        """Test valid tool configuration."""
        tool_config = ToolConfigModel(
            name='test_tool',
            prefilled_params={'param1': 'value1'},
            name_override='custom_tool',
            description_override='Custom description',
        )
        assert tool_config.name == 'test_tool'
        assert tool_config.prefilled_params == {'param1': 'value1'}
        assert tool_config.name_override == 'custom_tool'
        assert tool_config.description_override == 'Custom description'

    def test_tool_config_missing_name(self):
        """Test that tool config must have name."""
        with pytest.raises(ValidationError):
            ToolConfigModel(
                prefilled_params={'param1': 'value1'},
            )

    def test_tool_config_minimal(self):
        """Test tool config with only required field."""
        tool_config = ToolConfigModel(name='test_tool')
        assert tool_config.name == 'test_tool'
        assert tool_config.prefilled_params is None
        assert tool_config.name_override is None
        assert tool_config.description_override is None


class TestAgentConfigModel:
    """Test cases for AgentConfigModel validation."""

    def test_valid_agent_with_job(self):
        """Test valid agent configuration with job field."""
        agent = AgentConfigModel(
            name='Test Agent',
            job='You are a helpful assistant',
        )
        assert agent.name == 'Test Agent'
        assert agent.job == 'You are a helpful assistant'

    def test_valid_agent_with_prompt(self):
        """Test valid agent configuration with prompt field."""
        agent = AgentConfigModel(
            name='Test Agent',
            prompt='You are a helpful assistant',
        )
        assert agent.name == 'Test Agent'
        assert agent.prompt == 'You are a helpful assistant'

    def test_agent_missing_job_and_prompt(self):
        """Test that agent must have either job or prompt."""
        with pytest.raises(
            ValueError, match="must have either 'job' or 'prompt' field"
        ):
            AgentConfigModel(name='Test Agent')

    def test_agent_with_both_job_and_prompt(self):
        """Test agent with both job and prompt (job takes precedence)."""
        agent = AgentConfigModel(
            name='Test Agent',
            job='Job description',
            prompt='Prompt description',
        )
        assert agent.job == 'Job description'
        assert agent.prompt == 'Prompt description'

    def test_agent_missing_name(self):
        """Test that agent must have name."""
        with pytest.raises(ValidationError):
            AgentConfigModel(job='You are a helpful assistant')

    def test_agent_with_model(self):
        """Test agent with model configuration."""
        agent = AgentConfigModel(
            name='Test Agent',
            job='You are a helpful assistant',
            model=LLMConfigModel(provider='openai', name='gpt-4'),
        )
        assert agent.model is not None
        assert agent.model.provider == 'openai'
        assert agent.model.name == 'gpt-4'

    def test_agent_with_settings(self):
        """Test agent with settings."""
        agent = AgentConfigModel(
            name='Test Agent',
            job='You are a helpful assistant',
            settings=SettingsModel(temperature=0.7, max_retries=3),
        )
        assert agent.settings is not None
        assert agent.settings.temperature == 0.7
        assert agent.settings.max_retries == 3

    def test_agent_with_tools_string_list(self):
        """Test agent with tools as string list."""
        agent = AgentConfigModel(
            name='Test Agent',
            job='You are a helpful assistant',
            tools=['tool1', 'tool2'],
        )
        assert agent.tools == ['tool1', 'tool2']

    def test_agent_with_tools_config_list(self):
        """Test agent with tools as ToolConfigModel list."""
        agent = AgentConfigModel(
            name='Test Agent',
            job='You are a helpful assistant',
            tools=[
                ToolConfigModel(name='tool1'),
                ToolConfigModel(name='tool2', prefilled_params={'param': 'value'}),
            ],
        )
        assert agent.tools is not None
        assert len(agent.tools) == 2
        assert isinstance(agent.tools[0], ToolConfigModel)
        assert isinstance(agent.tools[1], ToolConfigModel)
        assert agent.tools[0].name == 'tool1'
        assert agent.tools[1].name == 'tool2'

    def test_agent_with_mixed_tools(self):
        """Test agent with mixed tool types (strings and configs)."""
        agent = AgentConfigModel(
            name='Test Agent',
            job='You are a helpful assistant',
            tools=[
                'tool1',
                ToolConfigModel(name='tool2'),
            ],
        )
        assert agent.tools is not None
        assert len(agent.tools) == 2
        assert agent.tools[0] == 'tool1'
        assert isinstance(agent.tools[1], ToolConfigModel)
        assert agent.tools[1].name == 'tool2'

    def test_agent_tools_missing_name(self):
        """Test that tool configs in tools list must have name."""
        with pytest.raises(ValueError, match="must have a 'name' field"):
            AgentConfigModel(
                name='Test Agent',
                job='You are a helpful assistant',
                tools=[{'prefilled_params': {'param': 'value'}}],  # type: ignore[arg-type]
            )

    def test_agent_tools_invalid_type(self):
        """Test that tools must be strings or dicts with name."""
        with pytest.raises(ValueError, match='Invalid tool configuration type'):
            AgentConfigModel(
                name='Test Agent',
                job='You are a helpful assistant',
                tools=[123],  # type: ignore[arg-type]
            )

    def test_agent_with_parser(self):
        """Test agent with parser configuration."""
        agent = AgentConfigModel(
            name='Test Agent',
            job='You are a helpful assistant',
            parser=ParserModel(
                name='test_parser',
                fields=[
                    ParserFieldModel(
                        name='query',
                        type='str',
                        description='Query string',
                    ),
                ],
            ),
        )
        assert agent.parser is not None
        assert agent.parser.name == 'test_parser'

    def test_agent_with_examples(self):
        """Test agent with examples."""
        agent = AgentConfigModel(
            name='Test Agent',
            job='You are a helpful assistant',
            examples=[
                ExampleModel(input='Hello', output='Hi there!'),
                ExampleModel(input='How are you?', output={'status': 'good'}),
            ],
        )
        assert agent.examples is not None
        assert len(agent.examples) == 2
        assert agent.examples[0].input == 'Hello'
        assert agent.examples[1].output == {'status': 'good'}


class TestAgentYamlModel:
    """Test cases for AgentYamlModel validation."""

    def test_valid_yaml_minimal(self):
        """Test valid minimal YAML configuration."""
        yaml_data = {
            'agent': {
                'name': 'Test Agent',
                'job': 'You are a helpful assistant',
            }
        }
        config = AgentYamlModel(**yaml_data)  # type: ignore[arg-type]
        assert config.agent.name == 'Test Agent'
        assert config.agent.job == 'You are a helpful assistant'
        assert config.metadata is None

    def test_valid_yaml_with_metadata(self):
        """Test valid YAML with metadata."""
        yaml_data = {
            'metadata': {
                'name': 'test-agent',
                'version': '1.0.0',
                'description': 'A test agent',
            },
            'agent': {
                'name': 'Test Agent',
                'job': 'You are a helpful assistant',
            },
        }
        config = AgentYamlModel(**yaml_data)  # type: ignore[arg-type]
        assert config.metadata is not None
        assert config.metadata.name == 'test-agent'
        assert config.metadata.version == '1.0.0'
        assert config.agent.name == 'Test Agent'

    def test_valid_yaml_full_config(self):
        """Test valid YAML with all fields."""
        yaml_data = {
            'metadata': {
                'name': 'test-agent',
                'version': '1.0.0',
                'description': 'A test agent',
                'author': 'Test Author',
                'tags': ['test', 'agent'],
            },
            'agent': {
                'name': 'Test Agent',
                'job': 'You are a helpful assistant',
                'role': 'assistant',
                'act_as': 'helpful AI',
                'model': {
                    'provider': 'openai',
                    'name': 'gpt-4',
                    'temperature': 0.7,
                    'max_tokens': 1000,
                },
                'settings': {
                    'temperature': 0.8,
                    'max_retries': 3,
                    'reasoning_pattern': 'REACT',
                },
                'tools': [
                    'tool1',
                    {'name': 'tool2', 'prefilled_params': {'param': 'value'}},
                ],
                'parser': {
                    'name': 'test_parser',
                    'fields': [
                        {
                            'name': 'query',
                            'type': 'str',
                            'description': 'Query string',
                        },
                    ],
                },
                'examples': [
                    {'input': 'Hello', 'output': 'Hi there!'},
                ],
            },
        }
        config = AgentYamlModel(**yaml_data)  # type: ignore[arg-type]
        assert config.metadata is not None
        assert config.metadata.name == 'test-agent'
        assert config.agent.name == 'Test Agent'
        assert config.agent.model is not None
        assert config.agent.model.provider == 'openai'
        assert config.agent.settings is not None
        assert config.agent.settings.max_retries == 3
        assert config.agent.tools is not None
        assert len(config.agent.tools) == 2
        assert config.agent.parser is not None
        assert config.agent.parser.name == 'test_parser'
        assert config.agent.examples is not None
        assert len(config.agent.examples) == 1

    def test_yaml_missing_agent(self):
        """Test that YAML must have agent section."""
        yaml_data = {
            'metadata': {
                'name': 'test-agent',
            },
        }
        with pytest.raises(ValidationError):
            AgentYamlModel(**yaml_data)  # type: ignore[arg-type]

    def test_yaml_from_string(self):
        """Test parsing YAML from string."""
        yaml_str = """
metadata:
  name: test-agent
  version: 1.0.0

agent:
  name: Test Agent
  job: You are a helpful assistant
  model:
    provider: openai
    name: gpt-4
"""
        yaml_data = yaml.safe_load(yaml_str)
        config = AgentYamlModel(**yaml_data)  # type: ignore[arg-type]
        assert config.metadata is not None
        assert config.metadata.name == 'test-agent'
        assert config.agent.name == 'Test Agent'
        assert config.agent.model is not None
        assert config.agent.model.provider == 'openai'

    def test_yaml_complex_parser(self):
        """Test YAML with complex nested parser."""
        yaml_str = """
agent:
  name: Test Agent
  job: You are a helpful assistant
  parser:
    name: complex_parser
    fields:
      - name: user
        type: object
        description: User object
        fields:
          - name: name
            type: str
            description: User name
          - name: addresses
            type: array
            description: User addresses
            items:
              name: address
              type: object
              description: Address object
              fields:
                - name: street
                  type: str
                  description: Street name
                - name: city
                  type: str
                  description: City name
"""
        yaml_data = yaml.safe_load(yaml_str)
        config = AgentYamlModel(**yaml_data)  # type: ignore[arg-type]
        assert config.agent.parser is not None
        assert config.agent.parser.fields[0].type == 'object'
        assert config.agent.parser.fields[0].fields is not None
        assert config.agent.parser.fields[0].fields[1].type == 'array'
        assert config.agent.parser.fields[0].fields[1].items is not None
        assert config.agent.parser.fields[0].fields[1].items.type == 'object'

    def test_yaml_literal_parser_field(self):
        """Test YAML with literal parser field."""
        yaml_str = """
agent:
  name: Test Agent
  job: You are a helpful assistant
  parser:
    name: status_parser
    fields:
      - name: status
        type: literal
        description: Status value
        values:
          - value: active
            description: Active status
          - value: inactive
            description: Inactive status
"""
        yaml_data = yaml.safe_load(yaml_str)
        config = AgentYamlModel(**yaml_data)  # type: ignore[arg-type]
        assert config.agent.parser is not None
        assert config.agent.parser.fields[0].type == 'literal'
        assert config.agent.parser.fields[0].values is not None
        assert len(config.agent.parser.fields[0].values) == 2
        assert config.agent.parser.fields[0].values[0].value == 'active'

    def test_yaml_all_providers(self):
        """Test YAML with different model providers."""
        providers = [
            ('openai', {'name': 'gpt-4'}),
            ('anthropic', {'name': 'claude-3-opus-20240229'}),
            ('claude', {'name': 'claude-3-opus-20240229'}),
            ('gemini', {'name': 'gemini-pro'}),
            ('google', {'name': 'gemini-pro'}),
            ('ollama', {'name': 'llama2', 'base_url': 'http://localhost:11434'}),
            (
                'vertexai',
                {
                    'name': 'gemini-pro',
                    'project': 'my-project',
                    'base_url': 'https://us-central1-aiplatform.googleapis.com',
                },
            ),
            ('rootflo', {'model_id': 'model-123'}),
            (
                'openai_vllm',
                {
                    'name': 'gpt-4',
                    'base_url': 'http://localhost:8000/v1',
                    'api_key': 'sk-test',
                },
            ),
        ]

        for provider, provider_config in providers:
            yaml_data = {
                'agent': {
                    'name': 'Test Agent',
                    'job': 'You are a helpful assistant',
                    'model': {'provider': provider, **provider_config},
                }
            }
            config = AgentYamlModel(**yaml_data)  # type: ignore[arg-type]
            assert config.agent.model is not None
            assert config.agent.model.provider == provider
