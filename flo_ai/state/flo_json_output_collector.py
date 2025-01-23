import json
import regex
from flo_ai.error.flo_exception import FloException
from typing import Dict, List, Any
from flo_ai.common.flo_logger import get_logger
from flo_ai.state.flo_output_collector import FloOutputCollector


class FloJsonOutputCollector(FloOutputCollector):
    def __init__(self, strict: bool = False):
        super().__init__()
        self.strict = strict
        self.data: List[Dict[str, Any]] = []

    def append(self, agent_output):
        self.data.append(self.__extract_jsons(agent_output))

    def __extract_jsons(self, llm_response):
        json_pattern = r'\{(?:[^{}]|(?R))*\}'
        json_matches = regex.findall(json_pattern, llm_response)
        json_object = {}
        for json_str in json_matches:
            try:
                json_obj = json.loads(json_str)
                json_object.update(json_obj)
            except json.JSONDecodeError as e:
                get_logger().error(f'Invalid JSON in response: {json_str}')
                raise e
        if self.strict and len(json_matches) == 0:
            raise FloException(
                'JSON response expected in collector model: strict', error_code=1099
            )
        return json_object

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
