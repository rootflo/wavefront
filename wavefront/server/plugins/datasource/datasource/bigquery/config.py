from dataclasses import dataclass
from typing import Optional


@dataclass
class BigQueryConfig:
    project_id: str
    dataset_id: str
    location: str
    credentials_path: Optional[str] = None
    credentials_json: Optional[dict] = None
