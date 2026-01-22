from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path, Query, Request, status
from fastapi.responses import JSONResponse

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from voice_agents_module.models.tool_schemas import (
    CreateToolPayload,
    UpdateToolPayload,
    AttachToolToAgentPayload,
    UpdateAgentToolPayload,
)
from voice_agents_module.services.tool_service import ToolService
from voice_agents_module.voice_agents_container import VoiceAgentsContainer

tool_router = APIRouter()


@tool_router.post('/v1/tools')
@inject
async def create_tool(
    request: Request,
    payload: CreateToolPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    tool_service: ToolService = Depends(Provide[VoiceAgentsContainer.tool_service]),
):
    """
    Create a new tool

    Creates a tool that can be attached to voice agents for function calling.

    Args:
        payload: Tool details including name, type, and configuration

    Returns:
        JSONResponse: Created tool details
    """
    tool = await tool_service.create_tool(payload)
    tool_dict = tool.to_dict(exclude_sensitive=True)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Tool created successfully', 'tool': tool_dict}
        ),
    )


@tool_router.get('/v1/tools')
@inject
async def list_tools(
    tool_type: str = Query(None, description='Filter by tool type (api, python)'),
    include_deleted: bool = Query(False, description='Include soft-deleted tools'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    tool_service: ToolService = Depends(Provide[VoiceAgentsContainer.tool_service]),
):
    """
    List all tools

    Returns:
        JSONResponse: List of all tools
    """
    tools = await tool_service.list_tools(
        include_deleted=include_deleted, tool_type=tool_type
    )
    tools_data = [tool.to_dict(exclude_sensitive=True) for tool in tools]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'tools': tools_data}),
    )


@tool_router.get('/v1/tools/{tool_id}')
@inject
async def get_tool(
    tool_id: UUID = Path(..., description='The ID of the tool'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    tool_service: ToolService = Depends(Provide[VoiceAgentsContainer.tool_service]),
):
    """
    Get a single tool by ID

    Args:
        tool_id: UUID of the tool to retrieve

    Returns:
        JSONResponse: Tool details
    """
    tool = await tool_service.get_tool(tool_id, exclude_sensitive=True)

    if not tool:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('Tool not found'),
        )

    tool_dict = tool.to_dict(exclude_sensitive=True)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'tool': tool_dict}),
    )


@tool_router.patch('/v1/tools/{tool_id}')
@inject
async def update_tool(
    tool_id: UUID,
    payload: UpdateToolPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    tool_service: ToolService = Depends(Provide[VoiceAgentsContainer.tool_service]),
):
    """
    Update a tool

    Args:
        tool_id: UUID of the tool to update
        payload: Fields to update

    Returns:
        JSONResponse: Updated tool details
    """
    tool = await tool_service.update_tool(tool_id, payload)
    tool_dict = tool.to_dict(exclude_sensitive=True)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Tool updated successfully', 'tool': tool_dict}
        ),
    )


@tool_router.delete('/v1/tools/{tool_id}')
@inject
async def delete_tool(
    tool_id: UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    tool_service: ToolService = Depends(Provide[VoiceAgentsContainer.tool_service]),
):
    """
    Delete a tool (soft delete)

    Args:
        tool_id: UUID of the tool to delete

    Returns:
        JSONResponse: Success message
    """
    await tool_service.delete_tool(tool_id)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Tool deleted successfully'}
        ),
    )


# Voice Agent Tool Association Endpoints


@tool_router.post('/v1/voice-agents/{agent_id}/tools')
@inject
async def attach_tool_to_agent(
    agent_id: UUID,
    payload: AttachToolToAgentPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    tool_service: ToolService = Depends(Provide[VoiceAgentsContainer.tool_service]),
):
    """
    Attach a tool to a voice agent

    Args:
        agent_id: UUID of the voice agent
        payload: Tool attachment details

    Returns:
        JSONResponse: Created association details
    """
    association = await tool_service.attach_tool_to_agent(agent_id, payload)
    assoc_dict = association.to_dict()

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Tool attached to agent successfully',
                'association': assoc_dict,
            }
        ),
    )


@tool_router.get('/v1/voice-agents/{agent_id}/tools')
@inject
async def get_agent_tools(
    agent_id: UUID,
    include_credentials: bool = Query(
        False, description='Include real credentials (for internal services)'
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    tool_service: ToolService = Depends(Provide[VoiceAgentsContainer.tool_service]),
):
    """
    Get all tools for a voice agent

    Args:
        agent_id: UUID of the voice agent
        include_credentials: If True, returns real credentials (default: False, returns masked)

    Returns:
        JSONResponse: List of tools with association details
    """
    tools = await tool_service.get_agent_tools(agent_id)

    if not include_credentials:
        # Mask credentials for frontend/external requests
        masked_tools = []
        for tool in tools:
            tool_copy = tool.copy()
            if 'config' in tool_copy and isinstance(tool_copy['config'], dict):
                if 'auth_credentials' in tool_copy['config']:
                    tool_copy['config']['auth_credentials'] = {'masked': True}
            masked_tools.append(tool_copy)
        tools = masked_tools

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'tools': tools}),
    )


@tool_router.patch('/v1/voice-agents/{agent_id}/tools/{tool_id}')
@inject
async def update_agent_tool(
    agent_id: UUID,
    tool_id: UUID,
    payload: UpdateAgentToolPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    tool_service: ToolService = Depends(Provide[VoiceAgentsContainer.tool_service]),
):
    """
    Update a tool association for a voice agent

    Args:
        agent_id: UUID of the voice agent
        tool_id: UUID of the tool
        payload: Fields to update

    Returns:
        JSONResponse: Updated association details
    """
    association = await tool_service.update_agent_tool(agent_id, tool_id, payload)
    assoc_dict = association.to_dict()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Tool association updated successfully',
                'association': assoc_dict,
            }
        ),
    )


@tool_router.delete('/v1/voice-agents/{agent_id}/tools/{tool_id}')
@inject
async def detach_tool_from_agent(
    agent_id: UUID,
    tool_id: UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    tool_service: ToolService = Depends(Provide[VoiceAgentsContainer.tool_service]),
):
    """
    Detach a tool from a voice agent

    Args:
        agent_id: UUID of the voice agent
        tool_id: UUID of the tool

    Returns:
        JSONResponse: Success message
    """
    await tool_service.detach_tool_from_agent(agent_id, tool_id)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Tool detached from agent successfully'}
        ),
    )
