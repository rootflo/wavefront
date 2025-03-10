from flo_ai import Flo, FloSession
from langchain_openai import ChatOpenAI
from flo_ai.tools.flo_tool import flotool
from flo_ai.error.flo_exception import FloException
from typing import List
import asyncio
import pytest


@pytest.fixture
def initialize_session():
    llm = ChatOpenAI(temperature=0, model_name='gpt-4o-mini', api_key='TEST_KEY')
    session = FloSession(llm)
    session.register_tool('adder', addition_tool)
    session.register_tool('muller', mul_tool)
    return session


@flotool(name='AdditionTool', description='Tool to add numbers')
async def addition_tool(numbers: List[int]) -> str:
    result = sum(numbers)
    await asyncio.sleep(1)
    return f'The sum is {result}'


@flotool(
    name='MultiplicationTool',
    description='Tool to multiply numbers to get product of numbers',
)
def mul_tool(numbers: List[int]) -> str:
    result = sum(numbers)
    return f'The product is {result}'


def test_valid_path(initialize_session):
    Flo.build(initialize_session, yaml_path='tests/test.yaml')


def test_invalid_path(initialize_session):
    try:
        yaml_path = 'test/test.yaml'
        Flo.build(initialize_session, yaml_path=yaml_path)
    except FloException as e:
        assert str(e) == f'[Error -1] YAML file at path {yaml_path} not found.'


def test_both_yaml(initialize_session):
    try:
        yaml_path = 'test/test.yaml'
        Flo.build(initialize_session, yaml='', yaml_path=yaml_path)
    except FloException as e:
        assert (
            str(e)
            == '[Error -1] Cannot specify both `yaml` and `yaml_path`. Use only one.'
        )
