from abc import ABC, abstractmethod
from typing import Any, Dict
from pathlib import Path
import json


class DataCollector(ABC):
    @abstractmethod
    def store_entry(self, entry: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def close(self) -> None:
        pass


class JSONLFileCollector(DataCollector):
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def store_entry(self, entry: Dict[str, Any]) -> None:
        with open(self.file_path, 'a') as f:
            json.dump(entry, f)
            f.write('\n')

    def close(self) -> None:
        pass
