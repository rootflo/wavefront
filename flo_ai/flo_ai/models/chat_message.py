from typing import Literal
from dataclasses import dataclass


@dataclass
class ChatMessage:
    role: Literal['user', 'assistant']
    content: str
