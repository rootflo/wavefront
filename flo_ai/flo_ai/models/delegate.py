from dataclasses import dataclass


@dataclass
class Delegate:
    to: list[str]
    retry: int = 1
