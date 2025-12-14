"""
Tests for arium YAML validation using Pydantic models.

This module tests all validation rules defined in flo_ai.models.arium,
ensuring that YAML configurations are properly validated before being used.
"""

import pytest
import yaml
from pydantic import ValidationError

from flo_ai.models.arium import (
    AriumYamlModel,
    AriumConfigModel,
    AriumAgentConfigModel,
    FunctionNodeConfigModel,
    RouterConfigModel,
    RouterSettingsModel,
    EdgeConfigModel,
    WorkflowConfigModel,
    AriumNodeConfigModel,
    ForEachNodeConfigModel,
)
from flo_ai.models.agent import LLMConfigModel


class TestAriumAgentConfigModel:
    """Test cases for AriumAgentConfigModel validation."""

    def test_valid_agent_with_direct_config(self):
        """Test valid agent with direct configuration."""
        agent = AriumAgentConfigModel(
            name='test_agent',
            role='Test Role',
            job='You are a test agent',
            model=LLMConfigModel(provider='openai', name='gpt-4o-mini'),
        )
        assert agent.name == 'test_agent'
        assert agent.role == 'Test Role'
        assert agent.job == 'You are a test agent'
        assert agent.model is not None

    def test_valid_agent_reference_only(self):
        """Test valid agent with only name (reference to pre-built agent)."""
        agent = AriumAgentConfigModel(name='prebuilt_agent')
        assert agent.name == 'prebuilt_agent'
        assert agent.job is None
        assert agent.yaml_config is None
        assert agent.yaml_file is None

    def test_valid_agent_with_yaml_config(self):
        """Test valid agent with inline yaml_config."""
        agent = AriumAgentConfigModel(
            name='yaml_agent',
            yaml_config='agent:\n  name: yaml_agent\n  job: Test job',
        )
        assert agent.name == 'yaml_agent'
        assert agent.yaml_config is not None
        assert agent.job is None

    def test_valid_agent_with_yaml_file(self):
        """Test valid agent with yaml_file reference."""
        agent = AriumAgentConfigModel(
            name='file_agent',
            yaml_file='path/to/agent.yaml',
        )
        assert agent.name == 'file_agent'
        assert agent.yaml_file == 'path/to/agent.yaml'
        assert agent.job is None

    def test_agent_multiple_config_methods(self):
        """Test that agent cannot have multiple configuration methods."""
        with pytest.raises(ValueError, match='multiple configuration methods'):
            AriumAgentConfigModel(
                name='invalid_agent',
                job='Direct job',
                yaml_config='agent:\n  name: test',
            )

    def test_agent_job_and_prompt_alias(self):
        """Test that job and prompt are aliases."""
        agent1 = AriumAgentConfigModel(
            name='agent1',
            job='Test job',
            model=LLMConfigModel(provider='openai', name='gpt-4o-mini'),
        )
        agent2 = AriumAgentConfigModel(
            name='agent2',
            prompt='Test job',
            model=LLMConfigModel(provider='openai', name='gpt-4o-mini'),
        )
        assert agent1.job == 'Test job'
        assert agent2.prompt == 'Test job'


class TestFunctionNodeConfigModel:
    """Test cases for FunctionNodeConfigModel validation."""

    def test_valid_function_node(self):
        """Test valid function node configuration."""
        node = FunctionNodeConfigModel(
            name='preprocessor',
            function_name='preprocess_data',
            description='Preprocesses input data',
            input_filter=['input1', 'input2'],
            prefilled_params={'param1': 'value1'},
        )
        assert node.name == 'preprocessor'
        assert node.function_name == 'preprocess_data'
        assert node.description == 'Preprocesses input data'
        assert node.input_filter == ['input1', 'input2']
        assert node.prefilled_params == {'param1': 'value1'}

    def test_minimal_function_node(self):
        """Test function node with only required fields."""
        node = FunctionNodeConfigModel(
            name='simple_node',
            function_name='simple_function',
        )
        assert node.name == 'simple_node'
        assert node.function_name == 'simple_function'
        assert node.description is None
        assert node.input_filter is None
        assert node.prefilled_params is None


class TestRouterConfigModel:
    """Test cases for RouterConfigModel validation."""

    def test_valid_smart_router(self):
        """Test valid smart router configuration."""
        router = RouterConfigModel(
            name='content_router',
            type='smart',
            routing_options={
                'technical_writer': 'Handle technical documentation',
                'creative_writer': 'Handle creative writing',
            },
            model=LLMConfigModel(provider='openai', name='gpt-4o-mini'),
        )
        assert router.name == 'content_router'
        assert router.type == 'smart'
        assert router.routing_options is not None
        assert len(router.routing_options) == 2

    def test_valid_reflection_router(self):
        """Test valid reflection router configuration."""
        router = RouterConfigModel(
            name='reflection_router',
            type='reflection',
            flow_pattern=['agent1', 'critic', 'agent1', 'final'],
            settings=RouterSettingsModel(allow_early_exit=False),
        )
        assert router.type == 'reflection'
        assert router.flow_pattern == ['agent1', 'critic', 'agent1', 'final']

    def test_valid_plan_execute_router(self):
        """Test valid plan-execute router configuration."""
        router = RouterConfigModel(
            name='plan_execute_router',
            type='plan_execute',
            agents={
                'planner': 'Creates plans',
                'developer': 'Implements code',
                'tester': 'Tests code',
            },
            settings=RouterSettingsModel(
                planner_agent='planner',
                executor_agent='developer',
                reviewer_agent='tester',
            ),
        )
        assert router.type == 'plan_execute'
        assert router.agents is not None
        assert len(router.agents) == 3

    def test_smart_router_missing_routing_options(self):
        """Test that smart router must have routing_options."""
        with pytest.raises(ValueError, match="must specify 'routing_options'"):
            RouterConfigModel(
                name='invalid_router',
                type='smart',
            )

    def test_reflection_router_missing_flow_pattern(self):
        """Test that reflection router must have flow_pattern."""
        with pytest.raises(ValueError, match="must specify 'flow_pattern'"):
            RouterConfigModel(
                name='invalid_router',
                type='reflection',
            )

    def test_plan_execute_router_missing_agents(self):
        """Test that plan_execute router must have agents."""
        with pytest.raises(ValueError, match="must specify 'agents'"):
            RouterConfigModel(
                name='invalid_router',
                type='plan_execute',
            )


class TestEdgeConfigModel:
    """Test cases for EdgeConfigModel validation."""

    def test_valid_edge(self):
        """Test valid edge configuration."""
        edge = EdgeConfigModel.model_validate(
            {'from': 'agent1', 'to': ['agent2', 'agent3'], 'router': 'content_router'}
        )
        assert edge.from_ == 'agent1'
        assert edge.to == ['agent2', 'agent3']
        assert edge.router == 'content_router'

    def test_edge_with_from_alias(self):
        """Test edge using 'from' and 'to' aliases."""
        edge_dict = {'from': 'agent1', 'to': ['agent2']}
        # When using dict, only 'from' and 'to' aliases are allowed (populate_by_name=False)
        edge = EdgeConfigModel.model_validate(edge_dict)
        assert edge.from_ == 'agent1'
        assert edge.to == ['agent2']

    def test_edge_without_router(self):
        """Test edge without router (direct connection)."""
        edge = EdgeConfigModel.model_validate({'from': 'agent1', 'to': ['agent2']})
        assert edge.router is None


class TestWorkflowConfigModel:
    """Test cases for WorkflowConfigModel validation."""

    def test_valid_workflow(self):
        """Test valid workflow configuration."""
        workflow = WorkflowConfigModel(
            start='agent1',
            edges=[
                EdgeConfigModel.model_validate({'from': 'agent1', 'to': ['agent2']}),
                EdgeConfigModel.model_validate({'from': 'agent2', 'to': ['agent3']}),
            ],
            end=['agent3'],
        )
        assert workflow.start == 'agent1'
        assert len(workflow.edges) == 2
        assert workflow.end == ['agent3']

    def test_workflow_with_from_alias_in_edges(self):
        """Test workflow with edges using 'from' and 'to' aliases."""
        workflow_dict = {
            'start': 'agent1',
            'edges': [
                {'from': 'agent1', 'to': ['agent2']},
                {'from': 'agent2', 'to': ['agent3']},
            ],
            'end': ['agent3'],
        }
        workflow = WorkflowConfigModel.model_validate(workflow_dict)
        assert workflow.start == 'agent1'
        assert len(workflow.edges) == 2
        assert workflow.edges[0].from_ == 'agent1'


class TestAriumNodeConfigModel:
    """Test cases for AriumNodeConfigModel validation."""

    def test_valid_arium_node_with_yaml_file(self):
        """Test valid arium node with yaml_file reference."""
        node = AriumNodeConfigModel(
            name='nested_workflow',
            yaml_file='path/to/workflow.yaml',
            inherit_variables=True,
        )
        assert node.name == 'nested_workflow'
        assert node.yaml_file == 'path/to/workflow.yaml'
        assert node.inherit_variables is True

    def test_valid_arium_node_with_inline_config(self):
        """Test valid arium node with inline configuration."""
        node = AriumNodeConfigModel(
            name='inline_workflow',
            agents=[
                AriumAgentConfigModel(
                    name='agent1',
                    job='Test job',
                    model=LLMConfigModel(provider='openai', name='gpt-4o-mini'),
                )
            ],
            workflow=WorkflowConfigModel(
                start='agent1',
                edges=[],
                end=['agent1'],
            ),
        )
        assert node.name == 'inline_workflow'
        assert node.agents is not None
        assert len(node.agents) == 1
        assert node.workflow is not None

    def test_arium_node_missing_config(self):
        """Test that arium node must have either yaml_file or inline config."""
        with pytest.raises(
            ValueError, match="must have either 'yaml_file' or inline configuration"
        ):
            AriumNodeConfigModel(
                name='invalid_node',
            )

    def test_arium_node_both_configs(self):
        """Test that arium node cannot have both yaml_file and inline config."""
        with pytest.raises(
            ValueError, match="cannot have both 'yaml_file' and inline configuration"
        ):
            AriumNodeConfigModel(
                name='invalid_node',
                yaml_file='path/to/file.yaml',
                agents=[
                    AriumAgentConfigModel(
                        name='agent1',
                        job='Test',
                        model=LLMConfigModel(provider='openai', name='gpt-4o-mini'),
                    )
                ],
                workflow=WorkflowConfigModel(
                    start='agent1',
                    edges=[],
                    end=['agent1'],
                ),
            )

    def test_arium_node_inline_config_missing_workflow(self):
        """Test that inline arium node must have workflow."""
        with pytest.raises(ValueError, match="must specify 'workflow'"):
            AriumNodeConfigModel(
                name='invalid_node',
                agents=[
                    AriumAgentConfigModel(
                        name='agent1',
                        job='Test',
                        model=LLMConfigModel(provider='openai', name='gpt-4o-mini'),
                    )
                ],
            )


class TestForEachNodeConfigModel:
    """Test cases for ForEachNodeConfigModel validation."""

    def test_valid_foreach_node(self):
        """Test valid foreach node configuration."""
        node = ForEachNodeConfigModel(
            name='batch_processor',
            execute_node='processor_agent',
        )
        assert node.name == 'batch_processor'
        assert node.execute_node == 'processor_agent'


class TestAriumConfigModel:
    """Test cases for AriumConfigModel validation."""

    def test_valid_arium_config_with_agents(self):
        """Test valid arium configuration with agents."""
        config = AriumConfigModel(
            agents=[
                AriumAgentConfigModel(
                    name='agent1',
                    job='Test job',
                    model=LLMConfigModel(provider='openai', name='gpt-4o-mini'),
                )
            ],
            workflow=WorkflowConfigModel(
                start='agent1',
                edges=[],
                end=['agent1'],
            ),
        )
        assert config.agents is not None
        assert len(config.agents) == 1
        assert config.workflow is not None

    def test_valid_arium_config_with_function_nodes(self):
        """Test valid arium configuration with function nodes."""
        config = AriumConfigModel(
            function_nodes=[
                FunctionNodeConfigModel(
                    name='func1',
                    function_name='function1',
                )
            ],
            workflow=WorkflowConfigModel(
                start='func1',
                edges=[],
                end=['func1'],
            ),
        )
        assert config.function_nodes is not None
        assert len(config.function_nodes) == 1

    def test_valid_arium_config_with_iterators(self):
        """Test valid arium configuration with iterators."""
        config = AriumConfigModel(
            agents=[
                AriumAgentConfigModel(
                    name='processor',
                    job='Process',
                    model=LLMConfigModel(provider='openai', name='gpt-4o-mini'),
                )
            ],
            iterators=[
                ForEachNodeConfigModel(
                    name='batch_processor',
                    execute_node='processor',
                )
            ],
            workflow=WorkflowConfigModel(
                start='batch_processor',
                edges=[],
                end=['batch_processor'],
            ),
        )
        assert config.iterators is not None
        assert len(config.iterators) == 1

    def test_arium_config_foreach_nodes_alias(self):
        """Test that foreach_nodes and iterators are aliases."""
        config_dict = {
            'agents': [
                {
                    'name': 'processor',
                    'job': 'Process',
                    'model': {'provider': 'openai', 'name': 'gpt-4o-mini'},
                }
            ],
            'foreach_nodes': [{'name': 'batch', 'execute_node': 'processor'}],
            'workflow': {
                'start': 'batch',
                'edges': [],
                'end': ['batch'],
            },
        }
        config = AriumConfigModel.model_validate(config_dict)
        # foreach_nodes should be merged into iterators
        assert config.iterators is not None
        assert config.iterators is not None and len(config.iterators) == 1

    def test_arium_config_no_nodes(self):
        """Test that arium config must have at least one node type."""
        with pytest.raises(ValueError, match='must have at least one of'):
            AriumConfigModel(
                workflow=WorkflowConfigModel(
                    start='agent1',
                    edges=[],
                    end=['agent1'],
                ),
            )


class TestAriumYamlModel:
    """Test cases for AriumYamlModel validation."""

    def test_valid_arium_yaml_minimal(self):
        """Test valid minimal arium YAML."""
        yaml_data = {
            'arium': {
                'agents': [
                    {
                        'name': 'agent1',
                        'job': 'Test job',
                        'model': {'provider': 'openai', 'name': 'gpt-4o-mini'},
                    }
                ],
                'workflow': {
                    'start': 'agent1',
                    'edges': [],
                    'end': ['agent1'],
                },
            }
        }
        config = AriumYamlModel.model_validate(yaml_data)
        assert config.arium is not None
        assert config.arium.agents is not None
        assert config.arium.agents is not None and len(config.arium.agents) == 1

    def test_valid_arium_yaml_with_metadata(self):
        """Test valid arium YAML with metadata."""
        yaml_data = {
            'metadata': {
                'name': 'test-workflow',
                'version': '1.0.0',
                'description': 'Test workflow',
            },
            'arium': {
                'agents': [
                    {
                        'name': 'agent1',
                        'job': 'Test job',
                        'model': {'provider': 'openai', 'name': 'gpt-4o-mini'},
                    }
                ],
                'workflow': {
                    'start': 'agent1',
                    'edges': [],
                    'end': ['agent1'],
                },
            },
        }
        config = AriumYamlModel.model_validate(yaml_data)
        assert config.metadata is not None
        assert config.metadata.name == 'test-workflow'
        assert config.arium is not None

    def test_valid_arium_yaml_complex(self):
        """Test valid complex arium YAML with all components."""
        yaml_data = {
            'metadata': {
                'name': 'complex-workflow',
                'version': '1.0.0',
            },
            'arium': {
                'agents': [
                    {
                        'name': 'agent1',
                        'job': 'Agent 1',
                        'model': {'provider': 'openai', 'name': 'gpt-4o-mini'},
                    },
                    {'name': 'agent2'},  # Reference to pre-built agent
                ],
                'function_nodes': [
                    {
                        'name': 'func1',
                        'function_name': 'function1',
                    }
                ],
                'routers': [
                    {
                        'name': 'router1',
                        'type': 'smart',
                        'routing_options': {
                            'agent1': 'Handle type 1',
                            'agent2': 'Handle type 2',
                        },
                    }
                ],
                'workflow': {
                    'start': 'agent1',
                    'edges': [
                        {
                            'from': 'agent1',
                            'to': ['agent2', 'func1'],
                            'router': 'router1',
                        },
                        {'from': 'agent2', 'to': ['end']},
                        {'from': 'func1', 'to': ['end']},
                    ],
                    'end': ['agent2', 'func1'],
                },
            },
        }
        config = AriumYamlModel.model_validate(yaml_data)
        assert config.arium.agents is not None
        assert config.arium.agents is not None and len(config.arium.agents) == 2
        assert config.arium.function_nodes is not None
        assert config.arium.routers is not None
        assert len(config.arium.routers) == 1
        assert len(config.arium.workflow.edges) == 3

    def test_arium_yaml_missing_arium_section(self):
        """Test that YAML must have arium section."""
        with pytest.raises(ValidationError):
            AriumYamlModel.model_validate({})

    def test_arium_yaml_from_string(self):
        """Test parsing arium YAML from string."""
        yaml_str = """
metadata:
  name: test-workflow
  version: 1.0.0

arium:
  agents:
    - name: agent1
      job: Test job
      model:
        provider: openai
        name: gpt-4o-mini
  workflow:
    start: agent1
    edges:
      - from: agent1
        to: [end]
    end: [agent1]
"""
        yaml_data = yaml.safe_load(yaml_str)
        config = AriumYamlModel.model_validate(yaml_data)
        assert config.metadata is not None
        assert config.metadata.name == 'test-workflow'
        assert config.arium.agents is not None
        assert config.arium.agents is not None and len(config.arium.agents) == 1


class TestAriumBuilderValidation:
    """Test cases for AriumBuilder YAML validation integration."""

    def test_builder_validation_method(self):
        """Test that AriumBuilder._validate_yaml_config works correctly."""
        from flo_ai.arium.builder import AriumBuilder

        valid_config = {
            'arium': {
                'agents': [
                    {
                        'name': 'agent1',
                        'job': 'Test job',
                        'model': {'provider': 'openai', 'name': 'gpt-4o-mini'},
                    }
                ],
                'workflow': {
                    'start': 'agent1',
                    'edges': [],
                    'end': ['agent1'],
                },
            }
        }
        # Should not raise validation error
        validated = AriumBuilder._validate_yaml_config(valid_config)
        assert validated is not None
        assert validated.arium is not None
        assert validated.arium.agents is not None
        assert len(validated.arium.agents) == 1

    def test_builder_validation_error_formatting(self):
        """Test that validation errors are properly formatted."""
        from flo_ai.arium.builder import AriumBuilder

        # Invalid router missing routing_options
        invalid_config = {
            'arium': {
                'routers': [
                    {
                        'name': 'invalid_router',
                        'type': 'smart',
                        # Missing routing_options
                    }
                ],
                'workflow': {
                    'start': 'agent1',
                    'edges': [],
                    'end': ['agent1'],
                },
            }
        }
        with pytest.raises(ValueError, match='YAML validation failed'):
            AriumBuilder._validate_yaml_config(invalid_config)

    def test_builder_validates_workflow_structure(self):
        """Test that builder validates workflow structure."""
        from flo_ai.arium.builder import AriumBuilder

        # Missing workflow section
        invalid_config = {
            'arium': {
                'agents': [
                    {
                        'name': 'agent1',
                        'job': 'Test',
                        'model': {'provider': 'openai', 'name': 'gpt-4o-mini'},
                    }
                ],
                # Missing workflow
            }
        }
        with pytest.raises(ValueError, match='YAML validation failed'):
            AriumBuilder._validate_yaml_config(invalid_config)

    def test_builder_validates_edge_structure(self):
        """Test that builder validates edge structure."""
        from flo_ai.arium.builder import AriumBuilder

        # Edge missing 'to' field
        invalid_config = {
            'arium': {
                'agents': [
                    {
                        'name': 'agent1',
                        'job': 'Test',
                        'model': {'provider': 'openai', 'name': 'gpt-4o-mini'},
                    }
                ],
                'workflow': {
                    'start': 'agent1',
                    'edges': [
                        {'from': 'agent1'}  # Missing 'to' field
                    ],
                    'end': ['agent1'],
                },
            }
        }
        with pytest.raises(ValueError, match='YAML validation failed'):
            AriumBuilder._validate_yaml_config(invalid_config)

    def test_builder_validates_missing_start_node(self):
        """Test that builder validates missing start node."""
        from flo_ai.arium.builder import AriumBuilder

        invalid_config = {
            'arium': {
                'agents': [
                    {
                        'name': 'agent1',
                        'job': 'Test',
                        'model': {'provider': 'openai', 'name': 'gpt-4o-mini'},
                    }
                ],
                'workflow': {
                    'edges': [],
                    'end': ['agent1'],
                    # Missing start
                },
            }
        }
        with pytest.raises(ValueError, match='YAML validation failed'):
            AriumBuilder._validate_yaml_config(invalid_config)

    def test_builder_validates_missing_end_nodes(self):
        """Test that builder validates missing end nodes."""
        from flo_ai.arium.builder import AriumBuilder

        invalid_config = {
            'arium': {
                'agents': [
                    {
                        'name': 'agent1',
                        'job': 'Test',
                        'model': {'provider': 'openai', 'name': 'gpt-4o-mini'},
                    }
                ],
                'workflow': {
                    'start': 'agent1',
                    'edges': [],
                    # Missing end
                },
            }
        }
        with pytest.raises(ValueError, match='YAML validation failed'):
            AriumBuilder._validate_yaml_config(invalid_config)

    def test_builder_validates_agent_missing_job_when_direct_config(self):
        """Test that builder validates agent missing job when using direct config."""
        from flo_ai.arium.builder import AriumBuilder

        invalid_config = {
            'arium': {
                'agents': [
                    {
                        'name': 'agent1',
                        'role': 'Test Agent',
                        'model': {'provider': 'openai', 'name': 'gpt-4o-mini'},
                        # Missing job/prompt
                    }
                ],
                'workflow': {
                    'start': 'agent1',
                    'edges': [],
                    'end': ['agent1'],
                },
            }
        }
        with pytest.raises(ValueError, match='YAML validation failed'):
            AriumBuilder._validate_yaml_config(invalid_config)

    def test_builder_validates_agent_multiple_config_methods(self):
        """Test that builder validates agent cannot have multiple config methods."""
        from flo_ai.arium.builder import AriumBuilder

        invalid_config = {
            'arium': {
                'agents': [
                    {
                        'name': 'agent1',
                        'job': 'Test job',
                        'yaml_config': 'agent:\n  name: test',
                        # Multiple config methods
                    }
                ],
                'workflow': {
                    'start': 'agent1',
                    'edges': [],
                    'end': ['agent1'],
                },
            }
        }
        with pytest.raises(ValueError, match='YAML validation failed'):
            AriumBuilder._validate_yaml_config(invalid_config)

    def test_builder_validates_function_node_missing_function_name(self):
        """Test that builder validates function node has function_name."""
        from flo_ai.arium.builder import AriumBuilder

        invalid_config = {
            'arium': {
                'function_nodes': [
                    {
                        'name': 'func1',
                        # Missing function_name
                    }
                ],
                'workflow': {
                    'start': 'func1',
                    'edges': [],
                    'end': ['func1'],
                },
            }
        }
        with pytest.raises(ValueError, match='YAML validation failed'):
            AriumBuilder._validate_yaml_config(invalid_config)

    def test_builder_validates_router_type_specific_requirements(self):
        """Test that builder validates router type-specific requirements."""
        from flo_ai.arium.builder import AriumBuilder

        # Test task_classifier missing task_categories
        invalid_config = {
            'arium': {
                'routers': [
                    {
                        'name': 'router1',
                        'type': 'task_classifier',
                        # Missing task_categories
                    }
                ],
                'workflow': {
                    'start': 'agent1',
                    'edges': [],
                    'end': ['agent1'],
                },
            }
        }
        with pytest.raises(ValueError, match='YAML validation failed'):
            AriumBuilder._validate_yaml_config(invalid_config)
