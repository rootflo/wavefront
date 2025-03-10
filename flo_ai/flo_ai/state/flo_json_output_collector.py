import json
import regex
from flo_ai.error.flo_exception import FloException
from typing import Dict, List, Any
from flo_ai.common.flo_logger import get_logger
from flo_ai.state.flo_output_collector import FloOutputCollector, CollectionStatus


class FloJsonOutputCollector(FloOutputCollector):
    def __init__(self, strict: bool = False):
        super().__init__()
        self.strict = strict
        self.status = CollectionStatus.success
        self.data: List[Dict[str, Any]] = []

    def append(self, agent_output):
        self.data.append(self.__extract_jsons(agent_output))

    def __strip_comments(self, json_str: str) -> str:
        cleaned = []
        length = len(json_str)
        i = 0

        while i < length:
            char = json_str[i]

            if char not in '"/*':
                cleaned.append(char)
                i += 1
                continue

            if char == '"':
                cleaned.append(char)
                i += 1

                while i < length:
                    char = json_str[i]
                    cleaned.append(char)
                    i += 1
                    if char == '"' and json_str[i - 2] != '\\':
                        break
                continue

            if char == '/' and i + 1 < length:
                next_char = json_str[i + 1]

                if next_char == '/':
                    i += 2
                    while i < length and json_str[i] != '\n':
                        i += 1
                    continue
                elif next_char == '*':
                    i += 2
                    while i + 1 < length:
                        if json_str[i] == '*' and json_str[i + 1] == '/':
                            i += 2
                            break
                        i += 1
                    continue

            cleaned.append(char)
            i += 1
        return ''.join(cleaned)

    def __extract_jsons(self, llm_response):
        json_pattern = r'\{(?:[^{}]|(?R))*\}'
        json_matches = regex.findall(json_pattern, llm_response)
        json_object = {}
        for json_str in json_matches:
            try:
                json_obj = json.loads(self.__strip_comments(json_str))
                json_object.update(json_obj)
            except json.JSONDecodeError as e:
                self.status = CollectionStatus.partial
                get_logger().error(f'Invalid JSON in response: {json_str}, {e}')
        if self.strict and len(json_matches) == 0:
            self.status = CollectionStatus.error
            get_logger().error(f'Error while finding json in -- {llm_response}')
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
