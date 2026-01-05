from dataclasses import asdict
from dataclasses import dataclass
from datetime import date
from enum import Enum
import math
from typing import Dict, List

from insights_module.models.insights_signal_query import Threshold


class AlertType(str, Enum):
    L7D = 'L7D'
    L30D = 'L30D'
    goal_line = 'goal_line'

    @staticmethod
    def resolve(type: str):
        if type == 'L7D':
            return AlertType.L7D
        if type == 'L30D':
            return AlertType.L30D
        if type == 'L90D':
            return AlertType.L30D
        if type == 'goal_line':
            return AlertType.goal_line
        else:
            return ValueError(f'Unknown alert type: {type}')


def serialize_values(value):
    if isinstance(value, date):
        return value.isoformat()  # Convert date to string ('YYYY-MM-DD')
    elif isinstance(value, Enum):
        return value.value  # Convert Enum to its string representation
    elif isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None  # Handle NaN, inf, -inf safely
    elif isinstance(value, list):
        return [serialize_values(v) for v in value]  # Recursively handle lists
    elif isinstance(value, dict):
        return {
            k: serialize_values(v) for k, v in value.items()
        }  # Recursively handle dicts
    return value  # Return other types as-is


@dataclass
class Alert:
    metric: str
    threshold: float
    previous_value: float
    current_value: float
    diff_value: float
    type: AlertType

    def to_dict(self):
        data = asdict(self)
        data['type'] = self.type.value
        return data


@dataclass
class Metric:
    metric: str
    name: str
    value: float


@dataclass
class ActionableAlerts:
    id: str
    title: str
    type: str
    name: str
    description: str
    alerts: List[Alert]

    def has_alerts(self):
        return len(self.alerts) > 0


@dataclass
class DataPoints:
    window_type: str
    old_window: Dict[str, List]
    new_window: Dict[str, List]


@dataclass
class DetailedInsights:
    metrices: List[Metric]
    data_points: DataPoints
    goal_lines: List[Threshold]

    def to_dict(self):
        return {
            'metrices': [asdict(m) for m in self.metrices],
            'data_points': serialize_values(asdict(self.data_points)),
            'goal_lines': [asdict(g) for g in self.goal_lines],
        }


@dataclass
class ActionableInsights:
    id: str
    title: str
    type: str
    name: str
    description: str
    alerts: List[Alert]
    details: DetailedInsights

    @staticmethod
    def to_actionable(alerts: ActionableAlerts, insights: DetailedInsights):
        return ActionableInsights(
            id=alerts.id,
            name=alerts.name,
            title=alerts.title,
            type=alerts.type,
            description=alerts.description,
            alerts=alerts.alerts,
            details=insights,
        )
