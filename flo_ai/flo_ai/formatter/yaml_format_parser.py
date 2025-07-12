import json
import csv
import yaml
from io import StringIO
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field, create_model
from dataclasses import dataclass


@dataclass
class ParseContract:
    name: str
    fields: List[Dict[str, Any]]


class FloJsonParser:
    def __init__(self, parse_contract: ParseContract):
        self.contract = parse_contract
        self._cached_models = {}
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

    def __create_nested_model(
        self, field_def: Dict[str, Any], model_name: str
    ) -> BaseModel:
        """Creates a nested Pydantic model for object types"""
        if model_name in self._cached_models:
            return self._cached_models[model_name]

        nested_fields = {}
        for nested_field in field_def['fields']:
            nested_type = self.__get_field_type_annotation(
                nested_field, f"{model_name}_{nested_field['name']}"
            )
            field_description = nested_field['description']
            nested_fields[nested_field['name']] = (
                nested_type,
                Field(..., description=field_description),
            )

        NestedModel = create_model(model_name, **nested_fields)
        self._cached_models[model_name] = NestedModel
        return NestedModel

    def __get_field_type_annotation(
        self, field: Dict[str, Any], model_name: str
    ) -> Any:
        """Determines the type annotation for a field, handling nested objects"""
        type_mapping = {
            'str': str,
            'int': int,
            'bool': bool,
            'float': float,
            'literal': self.__create_literal_type,
            'object': lambda f: self.__create_nested_model(f, model_name),
            'array': lambda f: List[
                self.__get_field_type_annotation(f['items'], f'{model_name}_item')
            ],
        }

        field_type = field['type']
        type_handler = type_mapping.get(field_type)

        if type_handler is None:
            raise ValueError(f'Unsupported type: {field_type}')

        return (
            type_handler(field)
            if field_type in ['literal', 'object', 'array']
            else type_handler
        )

    def __create_literal_type(self, field: Dict[str, Any]) -> Any:
        """Creates a Literal type from field definition"""
        literal_values = field.get('values', [])
        if not literal_values:
            raise ValueError(
                f"Field '{field['name']}' of type 'literal' must specify 'values'."
            )
        literals = [literal_value['value'] for literal_value in literal_values]
        return Literal[tuple(literals)]

    def get_format(self) -> BaseModel:
        return self.__create_contract_from_json()

    def __create_contract_from_json(self) -> BaseModel:
        pydantic_fields = {}
        for field in self.contract.fields:
            field_type = self.__get_field_type_annotation(
                field, f"{self.contract.name}_{field['name']}"
            )

            if field['type'] == 'literal':
                literal_values = field.get('values', [])
                default_prompt = field.get('default_value_prompt', '')
                field_description = f"""
                {field['description']}
                Following are the list of possibles values and its correponding description:
                {self.__dict_list_to_csv_string(literal_values)}

                This should be one of the values in the `value` column in the above csv.
                {default_prompt}
                """
            else:
                field_description = field['description']

            pydantic_fields[field['name']] = (
                field_type,
                Field(..., description=field_description),
            )

        DynamicModel = create_model(self.contract.name, **pydantic_fields)
        return DynamicModel

    @staticmethod
    def create(json_dict: Optional[Dict] = None, json_path: Optional[str] = None):
        return FloJsonParser.Builder(json_dict=json_dict, json_path=json_path).build()

    class Builder:
        def __init__(
            self, json_dict: Optional[Dict] = None, json_path: Optional[str] = None
        ):
            if json_dict is None and json_path is None:
                raise ValueError(
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


class FloYamlParser(FloJsonParser):
    """
    A parser class that handles YAML-based parser definitions for Flo agents.
    Extends FloJsonParser to reuse the model creation logic while adding YAML-specific functionality.
    """

    @staticmethod
    def create(yaml_dict: Optional[Dict] = None, yaml_path: Optional[str] = None):
        """
        Create a FloYamlParser instance from either a YAML dictionary or a YAML file path.

        Args:
            yaml_dict: A dictionary containing the YAML parser definition
            yaml_path: Path to a YAML file containing the parser definition

        Returns:
            FloYamlParser: A configured parser instance
        """
        return FloYamlParser.Builder(yaml_dict=yaml_dict, yaml_path=yaml_path).build()

    class Builder:
        def __init__(
            self, yaml_dict: Optional[Dict] = None, yaml_path: Optional[str] = None
        ):
            if yaml_dict is None and yaml_path is None:
                raise ValueError(
                    'Either yaml_dict or yaml_path is required to build a FloYamlParser'
                )
            self.yaml_dict = yaml_dict
            self.yaml_path = yaml_path

        def build(self):
            if self.yaml_dict:
                parser_def = self.yaml_dict
            else:
                with open(self.yaml_path) as f:
                    parser_def = yaml.safe_load(f)

            # Extract parser definition from agent YAML
            if 'agent' in parser_def and 'parser' in parser_def['agent']:
                parser_def = parser_def['agent']['parser']

            # Extract required fields
            name = parser_def['name']
            fields = parser_def['fields']

            # Process fields to handle examples and required flag
            processed_fields = []
            for field in fields:
                processed_field = field.copy()

                # Handle examples in literal values
                if field['type'] == 'literal' and 'values' in field:
                    for value in field['values']:
                        if 'examples' in value:
                            # Add examples to description
                            examples_str = '\nExamples:\n' + '\n'.join(
                                f'- {ex}' for ex in value['examples']
                            )
                            value['description'] = value['description'] + examples_str
                            del value['examples']

                # Remove required flag as it's not used in model creation
                if 'required' in processed_field:
                    del processed_field['required']

                processed_fields.append(processed_field)

            return FloYamlParser(ParseContract(name=name, fields=processed_fields))
