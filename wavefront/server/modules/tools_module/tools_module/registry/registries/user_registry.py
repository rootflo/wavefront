"""
User Tools Registry

Tools that read floware's user directory (users, group membership).
"""

from types import MethodType
from typing import Callable, Dict

from tools_module.floware_api import FlowareApiClient
from tools_module.users.user_api_tools import floware_list_users


def build_user_registry(api: FlowareApiClient) -> Dict[str, Callable]:
    """User tools bound to the floware API they should call."""
    return {'floware_list_users': MethodType(floware_list_users, api)}
