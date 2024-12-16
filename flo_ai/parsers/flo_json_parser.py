import json
import csv
from io import StringIO
from flo_ai.parsers.flo_parser import FloParser
from typing import List, Dict, Any, Optional, Literal
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

    def __dict_list_to_csv_string(self, data):
        if not data or len(data) == 0:
            return '```No data provided```'
        headers = data[0].keys()
        output = StringIO()

        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data)

        csv_string = output.getvalue()
        output.close()

        return f'```\n{csv_string}```'

    def __create_contract_from_json(self) -> BaseModel:
        type_mapping = {
            'str': str,
            'int': int,
            'bool': bool,
            'float': float,
            'literal': Literal,
        }
        pydantic_fields = {}
        for field in self.contract.fields:
            field_type = field['type']
            if field_type == 'literal':
                literal_values = field.get('values', [])
                if not literal_values:
                    raise ValueError(
                        f"Field '{field['name']}' of type 'literal' must specify 'values'."
                    )
                literals = [literal_value['value'] for literal_value in literal_values]
                field_type_annotation = Literal[tuple(literals)]
                default_prompt = (
                    field['default_value_prompt']
                    if 'default_value_prompt' in field
                    else ''
                )
                field_description = f"""
                {field['description']}
                Following are the list of possibles values and its correponding description:
                {self.__dict_list_to_csv_string(literal_values)}

                This should be one of the values in the `value` column in the above csv.
                {default_prompt}
                """
            else:
                field_type_annotation = type_mapping.get(field_type)
                if field_type_annotation is None:
                    raise ValueError(f'Unsupported type: {field_type}')
                field_description = field['description']

            pydantic_fields[field['name']] = (
                field_type_annotation,
                Field(..., description=field_description),
            )

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
