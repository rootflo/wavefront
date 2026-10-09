from types import MethodType
from typing import Callable, Dict

from tools_module.email.email_tool import send_email
from tools_module.floware_api import FlowareApiClient


def build_email_registry(api: FlowareApiClient) -> Dict[str, Callable]:
    return {'send_email': MethodType(send_email, api)}
