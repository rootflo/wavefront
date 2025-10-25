"""
Basic tests for the AriumBuilder to ensure it works correctly.
"""

import pytest
from unittest.mock import Mock
from flo_ai.arium.builder import AriumBuilder, create_arium
from flo_ai.arium.memory import MessageMemory
from flo_ai.models.agent import Agent
from flo_ai.tool.base_tool import Tool


class TestAriumBuilder:
    def test_builder_initialization(self):
        """Test that builder initializes correctly"""
        builder = AriumBuilder()
        assert builder._memory is None
        assert builder._agents == []
        assert builder._tools == []
        assert builder._start_node is None
        assert builder._end_nodes == []
        assert builder._edges == []
        assert builder._arium is None

    def test_create_arium_convenience_function(self):
        """Test the create_arium convenience function"""
        builder = create_arium()
        assert isinstance(builder, AriumBuilder)

    def test_add_agent(self):
        """Test adding a single agent"""
        builder = AriumBuilder()
        agent = Mock(spec=Agent)
        agent.name = 'test_agent'

        result = builder.add_agent(agent)
        assert result is builder  # Should return self for chaining
        assert agent in builder._agents

    def test_add_agents(self):
        """Test adding multiple agents"""
        builder = AriumBuilder()
        agents = [Mock(spec=Agent) for _ in range(3)]
        for i, agent in enumerate(agents):
            agent.name = f'agent_{i}'

        result = builder.add_agents(agents)
        assert result is builder
        assert all(agent in builder._agents for agent in agents)

    def test_add_tool(self):
        """Test adding a single tool"""
        builder = AriumBuilder()
        tool = Mock(spec=Tool)
        tool.name = 'test_tool'

        result = builder.add_tool(tool)
        assert result is builder
        assert tool in builder._tools

    def test_add_tools(self):
        """Test adding multiple tools"""
        builder = AriumBuilder()
        tools = [Mock(spec=Tool) for _ in range(3)]
        for i, tool in enumerate(tools):
            tool.name = f'tool_{i}'

        result = builder.add_tools(tools)
        assert result is builder
        assert all(tool in builder._tools for tool in tools)

    def test_with_memory(self):
        """Test setting custom memory"""
        builder = AriumBuilder()
        memory = Mock(spec=MessageMemory)

        result = builder.with_memory(memory)
        assert result is builder
        assert builder._memory is memory

    def test_start_with(self):
        """Test setting start node"""
        builder = AriumBuilder()
        agent = Mock(spec=Agent)
        agent.name = 'start_agent'

        result = builder.start_with(agent)
        assert result is builder
        assert builder._start_node is agent

    def test_end_with(self):
        """Test adding end node"""
        builder = AriumBuilder()
        agent = Mock(spec=Agent)
        agent.name = 'end_agent'

        result = builder.end_with(agent)
        assert result is builder
        assert agent in builder._end_nodes

        # Test that duplicate end nodes aren't added
        builder.end_with(agent)
        assert builder._end_nodes.count(agent) == 1

    def test_connect(self):
        """Test simple connection between nodes"""
        builder = AriumBuilder()
        agent1 = Mock(spec=Agent)
        agent1.name = 'agent1'
        agent2 = Mock(spec=Agent)
        agent2.name = 'agent2'

        result = builder.connect(agent1, agent2)
        assert result is builder
        assert (agent1, [agent2], None) in builder._edges

    def test_add_edge(self):
        """Test adding edge with router"""
        builder = AriumBuilder()
        agent1 = Mock(spec=Agent)
        agent1.name = 'agent1'
        agent2 = Mock(spec=Agent)
        agent2.name = 'agent2'

        def router(memory):
            return 'agent2'

        result = builder.add_edge(agent1, [agent2], router)
        assert result is builder
        assert (agent1, [agent2], router) in builder._edges

    def test_reset(self):
        """Test resetting the builder"""
        builder = AriumBuilder()

        # Add some data
        agent = Mock(spec=Agent)
        agent.name = 'test_agent'
        builder.add_agent(agent)
        builder.start_with(agent)

        # Reset and verify everything is cleared
        result = builder.reset()
        assert result is builder
        assert builder._memory is None
        assert builder._agents == []
        assert builder._tools == []
        assert builder._start_node is None
        assert builder._end_nodes == []
        assert builder._edges == []
        assert builder._arium is None

    def test_build_validation_no_nodes(self):
        """Test that build fails when no nodes are added"""
        builder = AriumBuilder()

        with pytest.raises(ValueError, match='No agents or tools added'):
            builder.build()

    def test_build_validation_no_start_node(self):
        """Test that build fails when no start node is specified"""
        builder = AriumBuilder()
        agent = Mock(spec=Agent)
        agent.name = 'test_agent'
        builder.add_agent(agent)

        with pytest.raises(ValueError, match='No start node specified'):
            builder.build()

    def test_build_validation_no_end_nodes(self):
        """Test that build fails when no end nodes are specified"""
        builder = AriumBuilder()
        agent = Mock(spec=Agent)
        agent.name = 'test_agent'
        builder.add_agent(agent)
        builder.start_with(agent)

        with pytest.raises(ValueError, match='No end nodes specified'):
            builder.build()

    def test_method_chaining(self):
        """Test that all methods return self for chaining"""
        builder = AriumBuilder()
        agent = Mock(spec=Agent)
        agent.name = 'test_agent'
        tool = Mock(spec=Tool)
        tool.name = 'test_tool'
        memory = Mock(spec=MessageMemory)

        # This should not raise any errors and should work with chaining
        result = (
            builder.with_memory(memory)
            .add_agent(agent)
            .add_tool(tool)
            .start_with(agent)
            .connect(agent, tool)
            .end_with(tool)
            .reset()
        )

        assert result is builder


if __name__ == '__main__':
    # Run a simple test
    test_builder = TestAriumBuilder()
    test_builder.test_builder_initialization()
    test_builder.test_add_agent()
    test_builder.test_method_chaining()
    print('Basic tests passed!')
