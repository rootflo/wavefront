"""
Tests for YAML-based Arium workflow construction.
"""

import pytest
from unittest.mock import Mock, patch

from flo_ai.arium.builder import AriumBuilder
from flo_ai.arium.memory import MessageMemory, BaseMemory
from flo_ai.models.agent import Agent
from flo_ai.tool.base_tool import Tool
from flo_ai.llm import OpenAI


class TestAriumYamlBuilder:
    """Test class for YAML-based Arium builder functionality."""

    def test_from_yaml_validation_no_params(self):
        """Test that from_yaml fails when no parameters are provided."""
        with pytest.raises(
            ValueError, match='Either yaml_str or yaml_file must be provided'
        ):
            AriumBuilder.from_yaml()

    def test_from_yaml_validation_both_params(self):
        """Test that from_yaml fails when both parameters are provided."""
        with pytest.raises(
            ValueError, match='Only one of yaml_str or yaml_file should be provided'
        ):
            AriumBuilder.from_yaml(yaml_str='test', yaml_file='test.yaml')

    def test_from_yaml_validation_missing_arium_section(self):
        """Test that from_yaml fails when YAML doesn't contain arium section."""
        yaml_config = """
        metadata:
          name: test
        """
        with pytest.raises(ValueError, match='YAML must contain an "arium" section'):
            AriumBuilder.from_yaml(yaml_str=yaml_config)

    def test_from_yaml_simple_configuration(self):
        """Test basic YAML configuration parsing."""
        yaml_config = """
        metadata:
          name: test-workflow
          version: 1.0.0
          description: "Test workflow"
          
        arium:
          agents:
            - name: test_agent
              yaml_config: |
                agent:
                  name: test_agent
                  job: "You are a test agent"
                  model:
                    provider: openai
                    name: gpt-4o-mini
                    
          workflow:
            start: test_agent
            edges:
              - from: test_agent
                to: [end]
            end: [test_agent]
        """

        # Mock the AgentBuilder.from_yaml to avoid actual LLM calls
        with patch('flo_ai.arium.builder.AgentBuilder') as mock_agent_builder:
            mock_agent = Mock(spec=Agent)
            mock_agent.name = 'test_agent'

            mock_builder_instance = Mock()
            mock_builder_instance.build.return_value = mock_agent
            mock_agent_builder.from_yaml.return_value = mock_builder_instance

            builder = AriumBuilder.from_yaml(yaml_str=yaml_config)

            # Verify the builder was configured correctly
            assert len(builder._agents) == 1
            assert builder._agents[0].name == 'test_agent'
            assert builder._start_node == mock_agent
            assert mock_agent in builder._end_nodes

    def test_from_yaml_with_custom_memory(self):
        """Test YAML configuration with custom memory parameter."""
        yaml_config = """
        arium:
          agents:
            - name: test_agent
              yaml_config: |
                agent:
                  name: test_agent
                  job: "You are a test agent"
                  model:
                    provider: openai
                    name: gpt-4o-mini
                    
          workflow:
            start: test_agent
            edges:
              - from: test_agent
                to: [end]
            end: [test_agent]
        """

        # Create custom memory
        custom_memory = Mock(spec=MessageMemory)

        with patch('flo_ai.arium.builder.AgentBuilder') as mock_agent_builder:
            mock_agent = Mock(spec=Agent)
            mock_agent.name = 'test_agent'

            mock_builder_instance = Mock()
            mock_builder_instance.build.return_value = mock_agent
            mock_agent_builder.from_yaml.return_value = mock_builder_instance

            builder = AriumBuilder.from_yaml(yaml_str=yaml_config, memory=custom_memory)

            # Verify custom memory was used
            assert builder._memory == custom_memory

    def test_from_yaml_default_memory(self):
        """Test that default MessageMemory is used when no memory is provided."""
        yaml_config = """
        arium:
          agents:
            - name: test_agent
              yaml_config: |
                agent:
                  name: test_agent
                  job: "You are a test agent"
                  model:
                    provider: openai
                    name: gpt-4o-mini
                    
          workflow:
            start: test_agent
            edges:
              - from: test_agent
                to: [end]
            end: [test_agent]
        """

        with patch('flo_ai.arium.builder.AgentBuilder') as mock_agent_builder:
            mock_agent = Mock(spec=Agent)
            mock_agent.name = 'test_agent'

            mock_builder_instance = Mock()
            mock_builder_instance.build.return_value = mock_agent
            mock_agent_builder.from_yaml.return_value = mock_builder_instance

            builder = AriumBuilder.from_yaml(yaml_str=yaml_config)

            # Verify default MessageMemory was created
            assert builder._memory is not None
            assert isinstance(builder._memory, MessageMemory)

    def test_from_yaml_with_tools(self):
        """Test YAML configuration with tools."""
        yaml_config = """
        arium:
          agents:
            - name: test_agent
              yaml_config: |
                agent:
                  name: test_agent
                  job: "Test agent with tools"
                  model:
                    provider: openai
                    name: gpt-4o-mini
                    
          tools:
            - name: test_tool
            
          workflow:
            start: test_agent
            edges:
              - from: test_agent
                to: [test_tool]
              - from: test_tool
                to: [end]
            end: [test_tool]
        """

        # Create mock tool
        mock_tool = Mock(spec=Tool)
        mock_tool.name = 'test_tool'
        tools = {'test_tool': mock_tool}

        with patch('flo_ai.arium.builder.AgentBuilder') as mock_agent_builder:
            mock_agent = Mock(spec=Agent)
            mock_agent.name = 'test_agent'

            mock_builder_instance = Mock()
            mock_builder_instance.build.return_value = mock_agent
            mock_agent_builder.from_yaml.return_value = mock_builder_instance

            builder = AriumBuilder.from_yaml(yaml_str=yaml_config, tools=tools)

            # Verify tools were added
            assert len(builder._tools) == 1
            assert builder._tools[0] == mock_tool

    def test_from_yaml_with_routers(self):
        """Test YAML configuration with custom routers."""
        yaml_config = """
        arium:
          agents:
            - name: agent1
              yaml_config: |
                agent:
                  name: agent1
                  job: "First agent"
                  model:
                    provider: openai
                    name: gpt-4o-mini
            - name: agent2
              yaml_config: |
                agent:
                  name: agent2
                  job: "Second agent"
                  model:
                    provider: openai
                    name: gpt-4o-mini
                    
          workflow:
            start: agent1
            edges:
              - from: agent1
                to: [agent2]
                router: test_router
              - from: agent2
                to: [end]
            end: [agent2]
        """

        # Create mock router
        def test_router(memory: BaseMemory) -> str:
            return 'agent2'

        routers = {'test_router': test_router}

        with patch('flo_ai.arium.builder.AgentBuilder') as mock_agent_builder:
            mock_agent1 = Mock(spec=Agent)
            mock_agent1.name = 'agent1'
            mock_agent2 = Mock(spec=Agent)
            mock_agent2.name = 'agent2'

            mock_builder_instance = Mock()
            mock_builder_instance.build.side_effect = [mock_agent1, mock_agent2]
            mock_agent_builder.from_yaml.return_value = mock_builder_instance

            builder = AriumBuilder.from_yaml(yaml_str=yaml_config, routers=routers)

            # Verify router was assigned
            assert len(builder._edges) == 1
            from_node, to_nodes, router = builder._edges[0]
            assert from_node == mock_agent1
            assert to_nodes == [mock_agent2]
            assert router == test_router

    def test_from_yaml_missing_tool_error(self):
        """Test error when referenced tool is not provided."""
        yaml_config = """
        arium:
          agents:
            - name: test_agent
              yaml_config: |
                agent:
                  name: test_agent
                  job: "Test agent"
                  model:
                    provider: openai
                    name: gpt-4o-mini
                    
          tools:
            - name: missing_tool
            
          workflow:
            start: test_agent
            edges:
              - from: test_agent
                to: [missing_tool]
              - from: missing_tool
                to: [end]
            end: [missing_tool]
        """

        with patch('flo_ai.arium.builder.AgentBuilder'):
            with pytest.raises(
                ValueError,
                match='Tool missing_tool not found in provided tools dictionary',
            ):
                AriumBuilder.from_yaml(yaml_str=yaml_config, tools={})

    def test_from_yaml_missing_router_error(self):
        """Test error when referenced router is not provided."""
        yaml_config = """
        arium:
          agents:
            - name: agent1
              yaml_config: |
                agent:
                  name: agent1
                  job: "Test agent"
                  model:
                    provider: openai
                    name: gpt-4o-mini
            - name: agent2
              yaml_config: |
                agent:
                  name: agent2
                  job: "Test agent"
                  model:
                    provider: openai
                    name: gpt-4o-mini
                    
          workflow:
            start: agent1
            edges:
              - from: agent1
                to: [agent2]
                router: missing_router
              - from: agent2
                to: [end]
            end: [agent2]
        """

        with patch('flo_ai.arium.builder.AgentBuilder'):
            with pytest.raises(
                ValueError,
                match='Router missing_router not found',
            ):
                AriumBuilder.from_yaml(yaml_str=yaml_config, routers={})

    def test_from_yaml_missing_start_node_error(self):
        """Test error when workflow doesn't specify start node."""
        yaml_config = """
        arium:
          agents:
            - name: test_agent
              yaml_config: |
                agent:
                  name: test_agent
                  job: "Test agent"
                  model:
                    provider: openai
                    name: gpt-4o-mini
                    
          workflow:
            edges: []
            end: [test_agent]
        """

        with patch('flo_ai.arium.builder.AgentBuilder'):
            with pytest.raises(ValueError, match='Workflow must specify a start node'):
                AriumBuilder.from_yaml(yaml_str=yaml_config)

    def test_from_yaml_missing_end_nodes_error(self):
        """Test error when workflow doesn't specify end nodes."""
        yaml_config = """
        arium:
          agents:
            - name: test_agent
              yaml_config: |
                agent:
                  name: test_agent
                  job: "Test agent"
                  model:
                    provider: openai
                    name: gpt-4o-mini
                    
          workflow:
            start: test_agent
            edges:
              - from: test_agent
                to: [end]
        """

        with patch('flo_ai.arium.builder.AgentBuilder'):
            with pytest.raises(ValueError, match='Workflow must specify end nodes'):
                AriumBuilder.from_yaml(yaml_str=yaml_config)

    def test_from_yaml_invalid_agent_config_error(self):
        """Test error when agent doesn't have yaml_config or yaml_file."""
        yaml_config = """
        arium:
          agents:
            - name: invalid_agent
              # Missing yaml_config or yaml_file
                    
          workflow:
            start: invalid_agent
            edges:
              - from: invalid_agent
                to: [end]
            end: [invalid_agent]
        """

        with pytest.raises(
            ValueError,
            match='Agent invalid_agent not found in provided agents dictionary',
        ):
            AriumBuilder.from_yaml(yaml_str=yaml_config)

    def test_from_yaml_external_file_reference(self):
        """Test YAML configuration with external agent file reference."""
        yaml_config = """
        arium:
          agents:
            - name: external_agent
              yaml_file: "path/to/agent.yaml"
                    
          workflow:
            start: external_agent
            edges:
              - from: external_agent
                to: [end]
            end: [external_agent]
        """

        with patch('flo_ai.arium.builder.AgentBuilder') as mock_agent_builder:
            mock_agent = Mock(spec=Agent)
            mock_agent.name = 'external_agent'

            mock_builder_instance = Mock()
            mock_builder_instance.build.return_value = mock_agent
            mock_agent_builder.from_yaml.return_value = mock_builder_instance

            AriumBuilder.from_yaml(yaml_str=yaml_config)

            # Verify AgentBuilder.from_yaml was called with yaml_file
            mock_agent_builder.from_yaml.assert_called_with(
                yaml_file='path/to/agent.yaml', base_llm=None
            )

    def test_from_yaml_with_base_llm(self):
        """Test YAML configuration with base LLM parameter."""
        yaml_config = """
        arium:
          agents:
            - name: test_agent
              yaml_config: |
                agent:
                  name: test_agent
                  job: "Test agent"
                    
          workflow:
            start: test_agent
            edges:
              - from: test_agent
                to: [end]
            end: [test_agent]
        """

        mock_llm = Mock(spec=OpenAI)

        with patch('flo_ai.arium.builder.AgentBuilder') as mock_agent_builder:
            mock_agent = Mock(spec=Agent)
            mock_agent.name = 'test_agent'

            mock_builder_instance = Mock()
            mock_builder_instance.build.return_value = mock_agent
            mock_agent_builder.from_yaml.return_value = mock_builder_instance

            AriumBuilder.from_yaml(yaml_str=yaml_config, base_llm=mock_llm)

            # Verify AgentBuilder.from_yaml was called with base_llm
            calls = mock_agent_builder.from_yaml.call_args_list
            assert len(calls) == 1
            call_args, call_kwargs = calls[0]
            assert 'yaml_str' in call_kwargs
            assert 'base_llm' in call_kwargs
            assert call_kwargs['base_llm'] == mock_llm
            # Just verify it contains the expected content
            assert 'agent:' in call_kwargs['yaml_str']
            assert 'name: test_agent' in call_kwargs['yaml_str']
            assert 'job: "Test agent"' in call_kwargs['yaml_str']

    def test_from_yaml_complex_workflow(self):
        """Test complex workflow with multiple agents, tools, and routers."""
        yaml_config = """
        metadata:
          name: complex-workflow
          version: 2.0.0
          
        arium:
          agents:
            - name: dispatcher
              yaml_config: |
                agent:
                  name: dispatcher
                  role: Dispatcher
                  job: "Route requests to appropriate handlers"
                  model:
                    provider: openai
                    name: gpt-4o-mini
            - name: processor
              yaml_config: |
                agent:
                  name: processor
                  role: Processor
                  job: "Process the data"
                  model:
                    provider: openai
                    name: gpt-4o-mini
            - name: summarizer
              yaml_config: |
                agent:
                  name: summarizer
                  role: Summarizer
                  job: "Create final summary"
                  model:
                    provider: openai
                    name: gpt-4o-mini
                    
          tools:
            - name: data_tool
            - name: analysis_tool
            
          workflow:
            start: dispatcher
            edges:
              - from: dispatcher
                to: [data_tool, analysis_tool, processor]
                router: dispatch_router
              - from: data_tool
                to: [summarizer]
              - from: analysis_tool
                to: [summarizer]
              - from: processor
                to: [summarizer]
              - from: summarizer
                to: [end]
            end: [summarizer]
        """

        # Create mocks
        def dispatch_router(memory: BaseMemory) -> str:
            return 'processor'

        mock_data_tool = Mock(spec=Tool)
        mock_data_tool.name = 'data_tool'
        mock_analysis_tool = Mock(spec=Tool)
        mock_analysis_tool.name = 'analysis_tool'

        tools = {'data_tool': mock_data_tool, 'analysis_tool': mock_analysis_tool}
        routers = {'dispatch_router': dispatch_router}

        with patch('flo_ai.arium.builder.AgentBuilder') as mock_agent_builder:
            mock_dispatcher = Mock(spec=Agent)
            mock_dispatcher.name = 'dispatcher'
            mock_processor = Mock(spec=Agent)
            mock_processor.name = 'processor'
            mock_summarizer = Mock(spec=Agent)
            mock_summarizer.name = 'summarizer'

            mock_builder_instance = Mock()
            mock_builder_instance.build.side_effect = [
                mock_dispatcher,
                mock_processor,
                mock_summarizer,
            ]
            mock_agent_builder.from_yaml.return_value = mock_builder_instance

            builder = AriumBuilder.from_yaml(
                yaml_str=yaml_config, tools=tools, routers=routers
            )

            # Verify all components were configured
            assert len(builder._agents) == 3
            assert len(builder._tools) == 2
            assert len(builder._edges) == 4  # 4 edge definitions
            assert builder._start_node == mock_dispatcher
            assert mock_summarizer in builder._end_nodes

    def test_from_yaml_end_keyword_handling(self):
        """Test proper handling of 'end' keyword in edge definitions."""
        yaml_config = """
        arium:
          agents:
            - name: test_agent
              yaml_config: |
                agent:
                  name: test_agent
                  job: "Test agent"
                  model:
                    provider: openai
                    name: gpt-4o-mini
                    
          workflow:
            start: test_agent
            edges:
              - from: test_agent
                to: [end]  # Should not create actual edge, handled by end nodes
            end: [test_agent]
        """

        with patch('flo_ai.arium.builder.AgentBuilder') as mock_agent_builder:
            mock_agent = Mock(spec=Agent)
            mock_agent.name = 'test_agent'

            mock_builder_instance = Mock()
            mock_builder_instance.build.return_value = mock_agent
            mock_agent_builder.from_yaml.return_value = mock_builder_instance

            builder = AriumBuilder.from_yaml(yaml_str=yaml_config)

            # Should not create any edges since only 'end' was in to_nodes
            assert len(builder._edges) == 0
            assert mock_agent in builder._end_nodes

    def test_from_yaml_direct_agent_configuration(self):
        """Test direct agent configuration without nested YAML."""
        yaml_config = """
        metadata:
          name: test-workflow
          version: 1.0.0
          
        arium:
          agents:
            - name: test_agent
              role: Test Agent
              job: "You are a test agent for validation"
              model:
                provider: openai
                name: gpt-4o-mini
                base_url: "https://api.openai.com/v1"
              settings:
                temperature: 0.5
                max_retries: 2
                reasoning_pattern: REACT
                
          workflow:
            start: test_agent
            edges:
              - from: test_agent
                to: [end]
            end: [test_agent]
        """

        with patch('flo_ai.llm.OpenAI') as mock_openai:
            mock_llm = Mock()
            mock_openai.return_value = mock_llm

            builder = AriumBuilder.from_yaml(yaml_str=yaml_config)

            # Verify the builder was configured correctly
            assert len(builder._agents) == 1
            agent = builder._agents[0]
            assert agent.name == 'test_agent'
            assert agent.role == 'Test Agent'
            assert (
                agent.system_prompt
                == 'You are Test Agent. You are a test agent for validation'
            )
            assert mock_llm.temperature == 0.5

    def test_from_yaml_direct_config_with_tools(self):
        """Test direct agent configuration with tools."""
        yaml_config = """
        arium:
          agents:
            - name: test_agent
              job: "Test agent with tools"
              model:
                provider: openai
                name: gpt-4o-mini
              tools: ["calculator", "web_search"]
                
          tools:
            - name: calculator
            - name: web_search
            
          workflow:
            start: test_agent
            edges:
              - from: test_agent
                to: [end]
            end: [test_agent]
        """

        # Create mock tools
        mock_calculator = Mock(spec=Tool)
        mock_calculator.name = 'calculator'
        mock_web_search = Mock(spec=Tool)
        mock_web_search.name = 'web_search'

        tools = {'calculator': mock_calculator, 'web_search': mock_web_search}

        with patch('flo_ai.llm.OpenAI') as mock_openai:
            mock_llm = Mock()
            mock_openai.return_value = mock_llm

            builder = AriumBuilder.from_yaml(yaml_str=yaml_config, tools=tools)

            # Verify agent was configured with tools
            assert len(builder._agents) == 1
            agent = builder._agents[0]
            assert len(agent.tools) == 2
            assert mock_calculator in agent.tools
            assert mock_web_search in agent.tools

    def test_from_yaml_direct_config_with_parser(self):
        """Test direct agent configuration with structured output parser."""
        yaml_config = """
        arium:
          agents:
            - name: test_agent
              job: "Test agent with structured output"
              model:
                provider: openai
                name: gpt-4o-mini
              parser:
                name: TestParser
                fields:
                  - name: result
                    type: str
                    description: "The result"
                  - name: confidence
                    type: float
                    description: "Confidence score"
                
          workflow:
            start: test_agent
            edges:
              - from: test_agent
                to: [end]
            end: [test_agent]
        """

        with patch('flo_ai.llm.OpenAI') as mock_openai:
            with patch(
                'flo_ai.formatter.yaml_format_parser.FloYamlParser'
            ) as mock_parser:
                mock_llm = Mock()
                mock_openai.return_value = mock_llm

                mock_parser_instance = Mock()
                mock_parser_instance.get_format.return_value = {'type': 'object'}
                mock_parser.create.return_value = mock_parser_instance

                builder = AriumBuilder.from_yaml(yaml_str=yaml_config)

                # Verify parser was configured
                assert len(builder._agents) == 1
                agent = builder._agents[0]
                assert agent.output_schema == {'type': 'object'}

    def test_from_yaml_mixed_configuration_methods(self):
        """Test mixing different agent configuration methods in one workflow."""
        yaml_config = """
        arium:
          agents:
            # Direct configuration
            - name: direct_agent
              role: Direct Agent
              job: "Directly configured agent"
              model:
                provider: openai
                name: gpt-4o-mini
                
            # Inline YAML configuration
            - name: yaml_agent
              yaml_config: |
                agent:
                  name: yaml_agent
                  role: YAML Agent
                  job: "YAML configured agent"
                  model:
                    provider: openai
                    name: gpt-4o-mini
                    
            # External file reference
            - name: file_agent
              yaml_file: "path/to/agent.yaml"
                
          workflow:
            start: direct_agent
            edges:
              - from: direct_agent
                to: [yaml_agent]
              - from: yaml_agent
                to: [file_agent]
              - from: file_agent
                to: [end]
            end: [file_agent]
        """

        with patch('flo_ai.llm.OpenAI') as mock_openai:
            with patch('flo_ai.arium.builder.AgentBuilder') as mock_agent_builder:
                mock_llm = Mock()
                mock_openai.return_value = mock_llm

                # Mock for inline YAML config
                mock_yaml_agent = Mock(spec=Agent)
                mock_yaml_agent.name = 'yaml_agent'

                # Mock for external file config
                mock_file_agent = Mock(spec=Agent)
                mock_file_agent.name = 'file_agent'

                mock_builder_instance = Mock()
                mock_builder_instance.build.side_effect = [
                    mock_yaml_agent,
                    mock_file_agent,
                ]
                mock_agent_builder.from_yaml.return_value = mock_builder_instance

                builder = AriumBuilder.from_yaml(yaml_str=yaml_config)

                # Verify all three agents were created
                assert len(builder._agents) == 3

                # Check direct agent
                direct_agent = next(
                    a for a in builder._agents if a.name == 'direct_agent'
                )
                assert direct_agent.role == 'Direct Agent'

                # Check other agents were added
                assert any(a.name == 'yaml_agent' for a in builder._agents)
                assert any(a.name == 'file_agent' for a in builder._agents)

    def test_from_yaml_direct_config_validation_errors(self):
        """Test validation errors for direct agent configuration."""

        # Test missing required field
        yaml_config_missing_job = """
        arium:
          agents:
            - name: test_agent
              role: Test Agent
              # missing job field
              model:
                provider: openai
                name: gpt-4o-mini
          workflow:
            start: test_agent
            edges: []
            end: [test_agent]
        """

        with pytest.raises(ValueError, match='Agent test_agent must have either'):
            AriumBuilder.from_yaml(yaml_str=yaml_config_missing_job)

        # Test invalid reasoning pattern
        yaml_config_invalid_pattern = """
        arium:
          agents:
            - name: test_agent
              job: "Test agent"
              model:
                provider: openai
                name: gpt-4o-mini
              settings:
                reasoning_pattern: INVALID_PATTERN
          workflow:
            start: test_agent
            edges: []
            end: [test_agent]
        """

        with patch('flo_ai.llm.OpenAI'):
            with pytest.raises(ValueError, match='Invalid reasoning pattern'):
                AriumBuilder.from_yaml(yaml_str=yaml_config_invalid_pattern)

        # Test missing model when no base_llm provided
        yaml_config_missing_model = """
        arium:
          agents:
            - name: test_agent
              job: "Test agent"
              # missing model field
          workflow:
            start: test_agent
            edges: []
            end: [test_agent]
        """

        with pytest.raises(ValueError, match='Model must be specified'):
            AriumBuilder.from_yaml(yaml_str=yaml_config_missing_model)

    def test_from_yaml_direct_config_with_base_llm(self):
        """Test direct agent configuration with base LLM override."""
        yaml_config = """
        arium:
          agents:
            - name: test_agent
              job: "Test agent without model config"
              settings:
                temperature: 0.7
                
          workflow:
            start: test_agent
            edges: []
            end: [test_agent]
        """

        mock_base_llm = Mock(spec=OpenAI)

        builder = AriumBuilder.from_yaml(yaml_str=yaml_config, base_llm=mock_base_llm)

        # Verify agent was created with base LLM
        assert len(builder._agents) == 1
        agent = builder._agents[0]
        assert agent.llm == mock_base_llm
        assert mock_base_llm.temperature == 0.7

    def test_from_yaml_prebuilt_agents(self):
        """Test using pre-built agents with YAML workflow."""
        yaml_config = """
        arium:
          agents:
            # Reference pre-built agents (only name specified)
            - name: prebuilt_agent1
            - name: prebuilt_agent2
            
          workflow:
            start: prebuilt_agent1
            edges:
              - from: prebuilt_agent1
                to: [prebuilt_agent2]
              - from: prebuilt_agent2
                to: [end]
            end: [prebuilt_agent2]
        """

        # Create mock pre-built agents
        mock_agent1 = Mock(spec=Agent)
        mock_agent1.name = 'prebuilt_agent1'
        mock_agent2 = Mock(spec=Agent)
        mock_agent2.name = 'prebuilt_agent2'

        prebuilt_agents = {
            'prebuilt_agent1': mock_agent1,
            'prebuilt_agent2': mock_agent2,
        }

        builder = AriumBuilder.from_yaml(yaml_str=yaml_config, agents=prebuilt_agents)

        # Verify pre-built agents were used
        assert len(builder._agents) == 2
        assert mock_agent1 in builder._agents
        assert mock_agent2 in builder._agents
        assert builder._start_node == mock_agent1
        assert mock_agent2 in builder._end_nodes

    def test_from_yaml_prebuilt_agents_missing_error(self):
        """Test error when referenced pre-built agent is not provided."""
        yaml_config = """
        arium:
          agents:
            - name: missing_agent
            
          workflow:
            start: missing_agent
            edges: []
            end: [missing_agent]
        """

        with pytest.raises(
            ValueError,
            match='Agent missing_agent not found in provided agents dictionary',
        ):
            AriumBuilder.from_yaml(yaml_str=yaml_config, agents={})

    def test_from_yaml_mixed_prebuilt_and_configured_agents(self):
        """Test mixing pre-built agents with other configuration methods."""
        yaml_config = """
        arium:
          agents:
            # Pre-built agent reference
            - name: prebuilt_agent
            
            # Direct configuration
            - name: direct_agent
              role: Direct Agent
              job: "Directly configured agent"
              model:
                provider: openai
                name: gpt-4o-mini
                
            # Inline YAML config
            - name: yaml_agent
              yaml_config: |
                agent:
                  name: yaml_agent
                  job: "YAML configured agent"
                  model:
                    provider: openai
                    name: gpt-4o-mini
                    
          workflow:
            start: prebuilt_agent
            edges:
              - from: prebuilt_agent
                to: [direct_agent]
              - from: direct_agent
                to: [yaml_agent]
              - from: yaml_agent
                to: [end]
            end: [yaml_agent]
        """

        # Create mock pre-built agent
        mock_prebuilt_agent = Mock(spec=Agent)
        mock_prebuilt_agent.name = 'prebuilt_agent'

        prebuilt_agents = {'prebuilt_agent': mock_prebuilt_agent}

        with patch('flo_ai.llm.OpenAI') as mock_openai:
            with patch('flo_ai.arium.builder.AgentBuilder') as mock_agent_builder:
                mock_llm = Mock()
                mock_openai.return_value = mock_llm

                # Mock for inline YAML config
                mock_yaml_agent = Mock(spec=Agent)
                mock_yaml_agent.name = 'yaml_agent'

                mock_builder_instance = Mock()
                mock_builder_instance.build.return_value = mock_yaml_agent
                mock_agent_builder.from_yaml.return_value = mock_builder_instance

                builder = AriumBuilder.from_yaml(
                    yaml_str=yaml_config, agents=prebuilt_agents
                )

                # Verify all agents were created/added
                assert len(builder._agents) == 3

                # Check pre-built agent
                assert mock_prebuilt_agent in builder._agents

                # Check direct agent was created
                direct_agent = next(
                    a for a in builder._agents if a.name == 'direct_agent'
                )
                assert direct_agent.role == 'Direct Agent'

                # Check YAML agent was added
                assert mock_yaml_agent in builder._agents

    def test_from_yaml_prebuilt_agents_parameter_validation(self):
        """Test parameter validation for pre-built agents."""
        yaml_config = """
        arium:
          agents:
            - name: test_agent
              # Has additional fields, so not a pure reference
              role: "Some Role"
              
          workflow:
            start: test_agent
            edges: []
            end: [test_agent]
        """

        # This should not be treated as a pre-built agent reference
        # because it has additional fields beyond just 'name'
        with patch('flo_ai.llm.OpenAI'):
            with pytest.raises(ValueError, match='Agent test_agent must have either'):
                AriumBuilder.from_yaml(yaml_str=yaml_config)

    def test_from_yaml_prebuilt_agents_with_tools_and_routers(self):
        """Test pre-built agents working together with tools and routers."""
        yaml_config = """
        arium:
          agents:
            - name: dispatcher
            - name: processor
            
          tools:
            - name: calculator
            
          workflow:
            start: dispatcher
            edges:
              - from: dispatcher
                to: [calculator, processor]
                router: smart_router
              - from: calculator
                to: [processor]
              - from: processor
                to: [end]
            end: [processor]
        """

        # Create mocks
        mock_dispatcher = Mock(spec=Agent)
        mock_dispatcher.name = 'dispatcher'
        mock_processor = Mock(spec=Agent)
        mock_processor.name = 'processor'

        mock_calculator = Mock(spec=Tool)
        mock_calculator.name = 'calculator'

        def smart_router(memory):
            return 'processor'

        prebuilt_agents = {'dispatcher': mock_dispatcher, 'processor': mock_processor}
        tools = {'calculator': mock_calculator}
        routers = {'smart_router': smart_router}

        builder = AriumBuilder.from_yaml(
            yaml_str=yaml_config, agents=prebuilt_agents, tools=tools, routers=routers
        )

        # Verify everything was configured correctly
        assert len(builder._agents) == 2
        assert len(builder._tools) == 1
        assert len(builder._edges) == 2
        assert mock_dispatcher in builder._agents
        assert mock_processor in builder._agents
        assert mock_calculator in builder._tools


if __name__ == '__main__':
    pytest.main([__file__])
