from typing import List
from pydantic import BaseModel, Field


class YamlValidationError(BaseModel):
    """One problem found in an agent or workflow YAML document"""

    path: str = Field(
        ...,
        description=(
            'Location of the problem in the document, such as '
            "'arium.workflow.edges[1].to[0]'. Empty for a problem with the "
            'document as a whole (for example, it is not valid YAML).'
        ),
    )
    message: str = Field(..., description='What is wrong, and how to fix it')


class YamlValidationResult(BaseModel):
    """Result of validating an agent or workflow YAML document"""

    valid: bool = Field(..., description='True when no errors were found')
    errors: List[YamlValidationError] = Field(
        default_factory=list, description='Every problem found; empty when valid'
    )
