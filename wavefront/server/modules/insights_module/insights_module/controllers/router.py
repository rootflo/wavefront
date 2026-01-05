from fastapi.routing import APIRouter
from insights_module.controllers.dynamic_query_controller import dynamic_query_router
from insights_module.controllers.pdo_controller import pdo_router

insights_router = APIRouter()
insights_router.include_router(dynamic_query_router, prefix='/v1/insights')
insights_router.include_router(pdo_router, prefix='/v1/insights')
