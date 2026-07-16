"""Pydantic schemas for tools module API responses and requests"""

from typing import Any, Dict, List
from pydantic import BaseModel, Field


# ===== Response Data Models (Inner data field content) =====


class ToolDetail(BaseModel):
    name: str = Field(..., description='Name of the tool')
    description: str = Field(..., description='Description of what the tool does')
    category: str = Field(..., description='Category of the tool')
    parameters: Dict[str, Any] = Field(..., description='Tool parameters schema')
    required: List[str] = Field(default_factory=list, description='Required parameters')
    prefill_values: List[str] = Field(
        default_factory=list, description='Pre-filled parameter values'
    )


class ToolsListData(BaseModel):
    tools: Dict[str, ToolDetail] = Field(
        ...,
        description='Dictionary mapping tool names to their metadata',
        examples=[
            {
                'datasource_insert_rows': {
                    'name': 'datasource_insert_rows',
                    'description': 'Insert rows into a datasource table',
                    'category': 'datasource',
                    'parameters': {},
                    'required': [],
                    'prefill_values': [],
                }
            }
        ],
    )
    count: int = Field(..., description='Total number of tools', examples=[10])


class ToolNamesData(BaseModel):
    tool_names: List[str] = Field(
        ...,
        description='List of available tool names',
        examples=[['datasource_insert_rows', 'querying_knowlegebase']],
    )
    count: int = Field(..., description='Total number of tools', examples=[2])


class ToolExecutionDetails(BaseModel):
    name: str = Field(..., description='Name of the tool')
    resource_name: str = Field(
        default='', description='Name of the resource (e.g. Datasource name)'
    )
    prefill_parameter_names: List[str] = Field(
        default_factory=list, description='Names of parameters that are pre-filled'
    )
    prefilled_value: Dict[str, Any] = Field(
        default_factory=dict,
        description='Map of parameter names to their pre-filled values',
    )
    required: List[str] = Field(default_factory=list, description='Required parameters')
    parameters: Dict[str, Any] = Field(..., description='Tool parameters schema')
    description: str = Field(..., description='Description of what the tool does')
    category: str = Field(..., description='Category of the tool')


class ToolDetailsData(BaseModel):
    tool_details: List[ToolExecutionDetails] = Field(
        ..., description='List of detailed tool information'
    )
    count: int = Field(..., description='Total number of tools', examples=[5])


class ToolMetadataData(BaseModel):
    tool: ToolDetail = Field(
        ...,
        description='Metadata for a specific tool',
        examples=[
            {
                'name': 'datasource_insert_rows',
                'description': 'Insert rows into a datasource table',
                'category': 'datasource',
                'parameters': {},
                'required': [],
                'prefill_values': [],
            }
        ],
    )


class ValidationResult(BaseModel):
    valid_tools: List[str] = Field(..., description='List of valid tool names')
    missing_tools: List[str] = Field(
        ..., description='List of missing/invalid tool names'
    )
    all_valid: bool = Field(..., description='Whether all tools are valid')
    total_checked: int = Field(..., description='Total number of tools checked')


class ValidationResultData(BaseModel):
    validation_result: ValidationResult = Field(..., description='Validation results')


# ===== Request Models =====


class ValidateToolsRequest(BaseModel):
    tool_names: List[str] = Field(
        ...,
        description='List of tool names to validate',
        examples=[['datasource_insert_rows', 'querying_knowlegebase']],
        min_length=1,
    )
