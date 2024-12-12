import json
from flo_ai.parsers.flo_parser import FloParser
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, create_model
from flo_ai.error.flo_exception import FloException
from langchain_core.output_parsers import PydanticOutputParser
from dataclasses import dataclass


@dataclass
class ParseContract:
    name: str
    fields: List[Dict[str, Any]]


class FloJsonParser(FloParser):
    def __init__(self, parse_contract: ParseContract):
        self.contract = parse_contract
        super().__init__()

    def __create_contract_from_json(self) -> BaseModel:
        type_mapping = {'str': str, 'int': int, 'bool': bool, 'float': float}
        pydantic_fields = {
            field['name']: (
                type_mapping[field['type']],
                Field(..., description=field['description']),
            )
            for field in self.contract.fields
        }
        DynamicModel = create_model(self.contract.name, **pydantic_fields)
        return DynamicModel

    def get_format_instructions(self):
        return PydanticOutputParser(
            pydantic_object=self.__create_contract_from_json()
        ).get_format_instructions()

    def create(json_dict: Optional[Dict] = None, json_path: Optional[str] = None):
        return FloJsonParser.Builder(json_dict=json_dict, json_path=json_path).build()

    class Builder:
        def __init__(
            self, json_dict: Optional[Dict] = None, json_path: Optional[str] = None
        ):
            if json_dict is None and json_path is None:
                raise FloException(
                    'Either of json_dict or json_path is required to build a FloJsonParser'
                )
            self.json_dict = json_dict
            self.json_path = json_path

        def build(self):
            if self.json_dict:
                name = self.json_dict['name']
                fields = self.json_dict['fields']
            else:
                with open(self.json_path) as f:
                    json_contract = json.load(f)
                name = json_contract['name']
                fields = json_contract['fields']
            return FloJsonParser(ParseContract(name=name, fields=fields))
