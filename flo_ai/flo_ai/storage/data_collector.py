from abc import ABC, abstractmethod
from typing import Any, Dict
from pathlib import Path
import json


class DataCollector(ABC):
    @abstractmethod
    def store_log(self, entry: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def store_tool_log(self, entry: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def close(self) -> None:
        pass


class JSONLFileCollector(DataCollector):
    def __init__(self, folder_path: str):
        self.log_file_path = Path(f'{folder_path}/logs/logs.jsonl')
        self.tool_file_path = Path(f'{folder_path}/tools/tools.jsonl')

        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.tool_file_path.parent.mkdir(parents=True, exist_ok=True)

    def store_log(self, entry: Dict[str, Any]) -> None:
        with open(self.log_file_path, 'a') as f:
            json.dump(entry, f)
            f.write('\n')

    def store_tool_log(self, entry: Dict[str, Any]) -> None:
        with open(self.tool_file_path, 'a') as f:
            json.dump(entry, f)
            f.write('\n')

    def close(self) -> None:
        pass
