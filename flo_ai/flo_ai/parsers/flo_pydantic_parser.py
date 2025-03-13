from flo_ai.parsers.flo_parser import FloParser
from pydantic import BaseModel
from langchain_core.output_parsers import PydanticOutputParser


class FloPydanticParser(FloParser):
    def __init__(self, output_model: BaseModel):
        self.model = output_model
        super().__init__()

    def get_format_instructions(self):
        return PydanticOutputParser(
            pydantic_object=self.model
        ).get_format_instructions()

    def get_format(self):
        return self.model

    def create(output_model: BaseModel):
        return FloPydanticParser.Builder(output_model).build()

    class Builder:
        def __init__(self, output_model: BaseModel):
            self.model = output_model

        def build(self):
            return FloPydanticParser(self.model)
