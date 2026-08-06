"""
Configuration Tools Registry

Reads from wavefront's namespaced configuration store — static reference data a
deterministic step needs at execution time, kept out of both the workflow's code
and the caller's request.
"""

from tools_module.configurations.configuration_api_tools import fetch_configuration

CONFIGURATION_REGISTRY = {
    'fetch_configuration': fetch_configuration,
}
