from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List


@dataclass
class LeadQuery:
    product_category: str
    lead_type: str
    query: str
    periodicity: List[Dict[str, str]]


@dataclass
class QueryWindow:
    start: datetime
    end: datetime
