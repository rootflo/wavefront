from dataclasses import dataclass
from typing import Callable, List, Optional
from functools import partial
from flo_ai.arium.memory import BaseMemory


def default_router(
    to_node: str,
    memory: BaseMemory,
) -> str:
    return to_node


@dataclass
class StartNode:
    name = '__start__'
    input_filter: Optional[List[str]] = None


@dataclass
class EndNode:
    name = '__end__'
    input_filter: Optional[List[str]] = None


@dataclass
class Edge:
    router_fn: Callable | partial
    to_nodes: List[str]

    def is_default_router(self) -> bool:
        if isinstance(self.router_fn, partial):
            return self.router_fn.func.__name__ == 'default_router'
        return False
