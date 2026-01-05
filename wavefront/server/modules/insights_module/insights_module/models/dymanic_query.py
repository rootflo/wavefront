from dataclasses import dataclass
from dataclasses import field
from typing import List


@dataclass
class QueryParameter:
    name: str
    type: str


@dataclass
class QueryParameterValue:
    name: str
    value: str


@dataclass
class Query:
    id: str
    description: str
    query: str
    parameters: List[QueryParameter] = field(default_factory=list)


@dataclass
class DynamicQuery:
    id: str
    name: str
    queries: List[Query]
