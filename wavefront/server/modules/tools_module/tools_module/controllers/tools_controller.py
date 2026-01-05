from typing import Optional
from common_module.security import bearer_auth
from fastapi import APIRouter, HTTPException, Query, Depends, Security, status
from fastapi.responses import JSONResponse
from dependency_injector.wiring import Provide, inject
from common_module.response_formatter import ResponseFormatter
from common_module.common_container import CommonContainer
from common_module.models.response import GenericResponseModel, DataWrapper
from tools_module.services.tool_service import ToolService
from tools_module.tools_container import ToolsContainer
from tools_module.models.tool_schemas import (
    ToolsListData,
    ToolNamesData,
    ToolDetailsData,
    ToolMetadataData,
    ValidationResultData,
    ValidateToolsRequest,
)

tools_router = APIRouter(prefix='/v1/tools', tags=['Tools'])


@tools_router.get(
    '/',
    response_model=GenericResponseModel[DataWrapper[ToolsListData]],
    dependencies=[Security(bearer_auth)],
)
@inject
async def get_all_tools(
    category: Optional[str] = Query(
        None, description="Filter tools by category (e.g., 'datasource')"
    ),
    tool_service: ToolService = Depends(Provide[ToolsContainer.tool_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    Get all available tools with their metadata including parameters and descriptions
    """
    if category:
        tools = tool_service.get_tools_by_category(category)
        message = f"Retrieved tools for category '{category}'"
    else:
        tools = tool_service.get_available_tools()
        message = 'Retrieved all available tools'
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': message, 'data': {'tools': tools, 'count': len(tools)}}
        ),
    )


@tools_router.get(
    '/names',
    response_model=GenericResponseModel[DataWrapper[ToolNamesData]],
    dependencies=[Security(bearer_auth)],
)
@inject
async def get_tool_names(
    tool_service: ToolService = Depends(Provide[ToolsContainer.tool_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    Get list of available tool names only
    """
    tool_names = tool_service.get_tool_names()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Retrieved available tool names',
                'data': {'tool_names': tool_names, 'count': len(tool_names)},
            }
        ),
    )


@tools_router.get(
    '/tool-details',
    response_model=GenericResponseModel[DataWrapper[ToolDetailsData]],
    dependencies=[Security(bearer_auth)],
)
@inject
async def get_tool_details(
    tool_service: ToolService = Depends(Provide[ToolsContainer.tool_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    Get list of available tool details
    """
    tool_details_models = await tool_service.get_all_tool_details()
    tool_details = [t.model_dump() for t in tool_details_models]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Retrieved available tool names',
                'data': {'tool_details': tool_details, 'count': len(tool_details)},
            }
        ),
    )


@tools_router.get(
    '/{tool_name}',
    response_model=GenericResponseModel[DataWrapper[ToolMetadataData]],
    dependencies=[Security(bearer_auth)],
)
@inject
async def get_tool_by_name(
    tool_name: str,
    tool_service: ToolService = Depends(Provide[ToolsContainer.tool_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    Get metadata for a specific tool by name
    """
    tool_metadata = tool_service.get_tool_metadata(tool_name)

    if not tool_metadata:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': f"Retrieved tool metadata for '{tool_name}'",
                'data': {'tool': tool_metadata},
            }
        ),
    )


@tools_router.post(
    '/validate',
    response_model=GenericResponseModel[DataWrapper[ValidationResultData]],
    dependencies=[Security(bearer_auth)],
)
@inject
async def validate_tools(
    request: ValidateToolsRequest,
    tool_service: ToolService = Depends(Provide[ToolsContainer.tool_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    Validate that a list of tool names exist
    """
    missing_tools = tool_service.validate_tools_exist(request.tool_names)
    valid_tools = [name for name in request.tool_names if name not in missing_tools]
    all_valid = len(missing_tools) == 0

    message = (
        'All tools are valid'
        if all_valid
        else f'Found {len(missing_tools)} invalid tools'
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': message,
                'data': {
                    'validation_result': {
                        'valid_tools': valid_tools,
                        'missing_tools': missing_tools,
                        'all_valid': all_valid,
                        'total_checked': len(request.tool_names),
                    }
                },
            }
        ),
    )
