"""
Configuration Tools Registry

Reads from wavefront's namespaced configuration store — static reference data a
deterministic step needs at execution time, kept out of both the workflow's code
and the caller's request.
"""

from types import MethodType
from typing import Callable, Dict

from tools_module.configurations.configuration_api_tools import fetch_configuration
from tools_module.floware_api import FlowareApiClient


def build_configuration_registry(api: FlowareApiClient) -> Dict[str, Callable]:
    return {'fetch_configuration': MethodType(fetch_configuration, api)}
