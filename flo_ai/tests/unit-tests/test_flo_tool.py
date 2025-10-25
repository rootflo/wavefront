#!/usr/bin/env python3
"""
Pytest tests for the @flo_tool decorator.
"""

import sys
import os
import pytest

# Add the flo_ai directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flo_ai.tool import flo_tool


@flo_tool(
    description='Add two numbers together',
    parameter_descriptions={'a': 'First number to add', 'b': 'Second number to add'},
)
async def add_numbers(a: float, b: float) -> float:
    """Add two numbers and return the result."""
    return a + b


@flo_tool()
async def multiply_numbers(x: int, y: int) -> int:
    """
    Multiply two integers.

    Args:
        x: First integer
        y: Second integer
    """
    return x * y


class TestFloToolDecorator:
    """Test class for @flo_tool decorator functionality."""

    @pytest.mark.asyncio
    async def test_function_calls_work_normally(self):
        """Test that decorated functions can be called normally."""
        result1 = await add_numbers(5, 3)
        assert result1 == 8.0

        result2 = await multiply_numbers(4, 7)
        assert result2 == 28

    @pytest.mark.asyncio
    async def test_tool_objects_are_accessible(self):
        """Test that tool objects are properly attached to decorated functions."""
        # Test add_numbers tool
        assert hasattr(add_numbers, 'tool')
        assert add_numbers.tool.name == 'add_numbers'
        assert add_numbers.tool.description == 'Add two numbers together'
        assert 'a' in add_numbers.tool.parameters
        assert 'b' in add_numbers.tool.parameters

        # Test multiply_numbers tool
        assert hasattr(multiply_numbers, 'tool')
        assert multiply_numbers.tool.name == 'multiply_numbers'
        # Should use docstring as description when none provided
        assert 'Multiply two integers' in multiply_numbers.tool.description
        assert 'x' in multiply_numbers.tool.parameters
        assert 'y' in multiply_numbers.tool.parameters

    @pytest.mark.asyncio
    async def test_tool_execution_works(self):
        """Test that tool.execute() method works correctly."""
        tool_result1 = await add_numbers.tool.execute(a=10, b=20)
        assert tool_result1 == 30.0

        tool_result2 = await multiply_numbers.tool.execute(x=6, y=8)
        assert tool_result2 == 48

    @pytest.mark.asyncio
    async def test_parameter_types_are_preserved(self):
        """Test that parameter types are correctly preserved in tool metadata."""
        # Check add_numbers parameters
        a_param = add_numbers.tool.parameters.get('a', {})
        assert a_param.get('type') == 'number'  # float should be mapped to number

        b_param = add_numbers.tool.parameters.get('b', {})
        assert b_param.get('type') == 'number'

        # Check multiply_numbers parameters
        x_param = multiply_numbers.tool.parameters.get('x', {})
        assert x_param.get('type') == 'integer'

        y_param = multiply_numbers.tool.parameters.get('y', {})
        assert y_param.get('type') == 'integer'

    @pytest.mark.asyncio
    async def test_parameter_descriptions_are_set(self):
        """Test that parameter descriptions are correctly set."""
        # add_numbers has explicit parameter descriptions
        a_param = add_numbers.tool.parameters.get('a', {})
        assert a_param.get('description') == 'First number to add'

        b_param = add_numbers.tool.parameters.get('b', {})
        assert b_param.get('description') == 'Second number to add'

        # multiply_numbers should have default descriptions or be inferred
        multiply_numbers.tool.parameters.get('x', {})
        multiply_numbers.tool.parameters.get('y', {})
        # At minimum, parameters should exist even if no explicit descriptions
        assert 'x' in multiply_numbers.tool.parameters
        assert 'y' in multiply_numbers.tool.parameters


class TestFloToolEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_zero_values(self):
        """Test functions with zero values."""
        result1 = await add_numbers(0, 0)
        assert result1 == 0.0

        result2 = await multiply_numbers(0, 5)
        assert result2 == 0

    @pytest.mark.asyncio
    async def test_negative_values(self):
        """Test functions with negative values."""
        result1 = await add_numbers(-5, 3)
        assert result1 == -2.0

        result2 = await multiply_numbers(-4, -7)
        assert result2 == 28

    @pytest.mark.asyncio
    async def test_large_values(self):
        """Test functions with large values."""
        result1 = await add_numbers(1000000, 2000000)
        assert result1 == 3000000.0

        result2 = await multiply_numbers(1000, 2000)
        assert result2 == 2000000
