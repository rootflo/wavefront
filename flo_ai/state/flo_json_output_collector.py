import json
from typing import Dict, List, Any
from flo_ai.state.flo_output_collector import FloOutputCollector


class FloJsonOutputCollector(FloOutputCollector):
    def __init__(self):
        super().__init__()
        self.data: List[Dict[str, Any]] = []

    def append(self, agent_output):
        output_dict = json.loads(self.__remove_after_braces(agent_output))
        self.data.append(output_dict)

    def __remove_after_braces(self, s: str) -> str:
        first_brace = s.find('{')
        last_brace = s.rfind('}')

        if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
            return s[first_brace : last_brace + 1]
        return s

    def pop(self):
        return self.data.pop()

    def peek(self):
        return self.data[-1] if len(self.data) > 0 else None

    def fetch(self):
        return self.__merge_data()

    def __merge_data(self):
        result = {}
        for d in self.data:
            result.update(d)
        return result
