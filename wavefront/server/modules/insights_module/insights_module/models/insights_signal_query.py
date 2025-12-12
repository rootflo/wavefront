from dataclasses import dataclass
from dataclasses import field
from typing import List

import dacite
import yaml


@dataclass
class Threshold:
    metric: str
    threshold: float


@dataclass
class Periodicity:
    period: str
    alerts: List[Threshold]


@dataclass
class Projection:
    sql: str
    metric: str
    name: str


@dataclass
class Projections:
    parent: List[Projection]
    children: List[Projection] = field(default_factory=list)


@dataclass
class Variable:
    name: str


@dataclass
class Query:
    sql: str
    variables: List[Variable] = field(default_factory=list)


@dataclass
class Plot:
    name: str
    metrices: List[Projection]


@dataclass
class SignalQuery:
    id: str
    name: str
    title: str
    description: str
    projections: Projections
    query: Query
    version: int
    type: str
    periodicity: List[Periodicity]
    plots: List[Plot]
    goal_lines: List[Threshold] = field(default_factory=list)


def load_yaml_to_signal(signals: str) -> SignalQuery:
    yaml_data = []
    for signal in signals:
        yaml_data.append(
            dacite.from_dict(
                data_class=SignalQuery,
                data={
                    'id': signal.id,
                    'name': signal.name,
                    'title': signal.title,
                    'description': signal.description,
                    'projections': signal.projections,
                    'query': signal.query,
                    'version': signal.version,
                    'type': signal.type,
                    'periodicity': signal.periodicity,
                    'plots': signal.plots,
                    'goal_lines': signal.goal_lines,
                },
            )
        )
    return yaml_data


def load_yaml_from_str(yaml_str: str) -> SignalQuery:
    yml_dict = yaml.safe_load(yaml_str)
    return dacite.from_dict(data_class=SignalQuery, data=yml_dict)


def load_from_dict(data: dict) -> SignalQuery:
    return dacite.from_dict(data_class=SignalQuery, data=data)
