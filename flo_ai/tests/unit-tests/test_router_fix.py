#!/usr/bin/env python3
"""
Quick test to verify the router type annotation fix works.
"""

import inspect
from typing import get_origin, get_args, Literal
from flo_ai.arium import create_llm_router
from flo_ai.llm import OpenAI


def test_router_type_annotation():
    """Test that our router functions have proper type annotations"""

    # Create a router with dummy LLM
    llm = OpenAI(model='gpt-4o-mini', api_key='dummy-key')
    router = create_llm_router(
        'smart',
        routing_options={
            'researcher': 'Research tasks',
            'analyst': 'Analysis tasks',
            'writer': 'Writing tasks',
        },
        llm=llm,
    )

    # Check the function signature
    sig = inspect.signature(router)
    return_annotation = sig.return_annotation

    print(f'Return annotation: {return_annotation}')
    print(f'Return annotation type: {type(return_annotation)}')

    # Check if it's a Literal type
    origin = get_origin(return_annotation)
    print(f'Origin: {origin}')
    print(f'Is Literal: {origin is Literal}')

    if origin is Literal:
        literal_values = list(get_args(return_annotation))
        print(f'Literal values: {literal_values}')
        assert True, 'Router function has correct Literal type annotation'
    else:
        print('❌ Not a Literal type!')
        assert False, 'Router function should have Literal type annotation'


def test_validation_logic():
    """Test the exact validation logic from base.py"""

    llm = OpenAI(model='gpt-4o-mini', api_key='dummy-key')
    router = create_llm_router(
        'smart',
        routing_options={'researcher': 'Research tasks', 'analyst': 'Analysis tasks'},
        llm=llm,
    )

    try:
        # Get the function signature (same as base.py)
        sig = inspect.signature(router)
        return_annotation = sig.return_annotation

        # Check if there's no return annotation
        if return_annotation == inspect.Signature.empty:
            print('❌ No return annotation')
            return False

        # Check if the return type is a Literal
        origin = get_origin(return_annotation)

        # In Python 3.8+, Literal types have get_origin() return typing.Literal
        if origin is Literal:
            # Extract the literal values
            literal_values = list(get_args(return_annotation))
            print(f'✅ Validation passed! Literal values: {literal_values}')
            assert True, 'Validation logic works correctly'
        else:
            print(f'❌ Validation failed! Origin is {origin}, not Literal')
            assert False, f'Validation failed! Origin is {origin}, not Literal'

    except Exception as e:
        print(f'❌ Exception during validation: {e}')
        assert False, f'Exception during validation: {e}'


if __name__ == '__main__':
    print('🧪 Testing Router Type Annotation Fix')
    print('=' * 50)

    print('\n1. Testing type annotation:')
    result1 = test_router_type_annotation()

    print('\n2. Testing validation logic:')
    result2 = test_validation_logic()

    print('\n' + '=' * 50)
    if result1 and result2:
        print('✅ All tests passed! Router type annotations are working correctly.')
    else:
        print('❌ Tests failed! Router type annotations need fixing.')
