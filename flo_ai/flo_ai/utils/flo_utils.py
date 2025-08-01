from typing import Dict, Any
import json
from flo_ai.utils.logger import logger


class FloUtils:
    @staticmethod
    def extract_jsons_from_string(data: str, strict: bool = False) -> Dict[str, Any]:
        """
        1) Find all balanced `{ … }` blocks via a custom parser
        2) Strip comments and json.loads() each
        3) Merge into one dict (later keys override earlier)
        4) On strict mode, raise FloException if no JSON found
        """

        # Custom function to find balanced braces since (?R) is not supported in Python re
        def find_balanced_braces(text):
            matches = []
            i = 0
            while i < len(text):
                if text[i] == '{':
                    start = i
                    brace_count = 1
                    j = i + 1
                    in_string = False
                    escape_next = False

                    while j < len(text) and brace_count > 0:
                        char = text[j]

                        if escape_next:
                            escape_next = False
                        elif char == '\\' and in_string:
                            escape_next = True
                        elif char == '"' and not escape_next:
                            in_string = not in_string
                        elif not in_string:
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                brace_count -= 1

                        j += 1

                    if brace_count == 0:
                        candidate = text[start:j]
                        # Try to validate it's actually JSON by attempting to parse
                        try:
                            cleaned = FloUtils.strip_comments_from_string(candidate)
                            json.loads(cleaned)
                            matches.append(candidate)
                            i = j  # Continue from after the valid JSON
                        except json.JSONDecodeError:
                            # Not valid JSON, try starting from the next character
                            i += 1
                    else:
                        # Unbalanced braces, try starting from the next character
                        i += 1
                else:
                    i += 1
            return matches

        matches = find_balanced_braces(data)
        merged: Dict[str, Any] = {}

        for json_str in matches:
            try:
                cleaned = FloUtils.strip_comments_from_string(json_str)
                obj = json.loads(cleaned)
                merged.update(obj)
            except json.JSONDecodeError as e:
                logger.error(f'Invalid JSON in response: {json_str}, {e}')

        if strict and not matches:
            logger.error(f'No JSON found in strict mode: {data}')
            raise ValueError(f'No JSON found in strict mode: {data}')

        return merged

    @staticmethod
    def strip_comments_from_string(data: str) -> str:
        """Remove JS-style comments (// and /*…*/) so json.loads() will succeed."""
        cleaned = []
        i = 0
        length = len(data)

        while i < length:
            char = data[i]

            if char not in '"/*':
                cleaned.append(char)
                i += 1
                continue

            if char == '"':
                cleaned.append(char)
                i += 1
                while i < length:
                    char = data[i]
                    cleaned.append(char)
                    i += 1
                    if char == '"' and (i < 2 or data[i - 2] != '\\'):
                        break
                continue

            if char == '/' and i + 1 < length:
                next_char = data[i + 1]
                if next_char == '/':
                    i += 2
                    while i < length and data[i] != '\n':
                        i += 1
                    continue
                elif next_char == '*':
                    i += 2
                    while i + 1 < length:
                        if data[i] == '*' and data[i + 1] == '/':
                            i += 2
                            break
                        i += 1
                    continue

            cleaned.append(char)
            i += 1

        return ''.join(cleaned)
