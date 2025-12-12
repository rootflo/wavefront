from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from common_module.response_formatter import ResponseFormatter
from common_module.common_container import CommonContainer
from dependency_injector.wiring import Provide, inject
from product_analysis_module.models.product_analysis import (
    CreateProductAnalysisPayload,
    ProductAnalysis,
)
from user_management_module.utils.user_utils import get_current_user, check_is_admin
from datetime import datetime
from product_analysis_module.product_analysis_container import ProductAnalysisContainer
from product_analysis_module.product_analysis_service import ProductAnalysisService


product_analysis_router = APIRouter(prefix='/v1')


@product_analysis_router.post('/product-analysis')
@inject
async def create_product_analysis(
    request: Request,
    payload: CreateProductAnalysisPayload,
    product_analysis_service: ProductAnalysisService = Depends(
        Provide[ProductAnalysisContainer.product_analysis_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    This endpoint is used to create a product analysis event.
    """

    user_role, user_id, session_id = get_current_user(request)
    if not user_id:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    # Create ProductAnalysis object from the payload with server-added fields
    product_analysis = ProductAnalysis(
        event_name=payload.event_name,
        type=payload.type,
        sub_type=payload.sub_type,
        category=payload.category,
        sub_category=payload.sub_category,
        action=payload.action,
        action_type=payload.action_type,
        page=payload.page,
        page_path=payload.page_path,
        matadata=payload.matadata,
        user_id=user_id,
        user_role=user_role,
        session_id=session_id,
        created_at=datetime.now(),
    )

    await product_analysis_service.create_product_analysis(product_analysis)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {'message': 'The event has been logged successfully'}
        ),
    )


@product_analysis_router.get('/product-analysis')
@inject
async def get_product_analysis(
    request: Request,
    product_analysis_service: ProductAnalysisService = Depends(
        Provide[ProductAnalysisContainer.product_analysis_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    This endpoint is used to get the product analysis events if the user is an admin.
    """
    user_role_id, user_id, _ = get_current_user(request)
    user_role = await check_is_admin(user_role_id)

    if not user_id or not user_role:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    product_analysis = await product_analysis_service.get_product_analysis()
    product_analysis_response = [item.to_dict() for item in product_analysis]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'product_analysis': product_analysis_response}
        ),
    )
