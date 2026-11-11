from deprecated_api_module.controllers.image_controller import image_controller
from fastapi.routing import APIRouter

deprecated_api_router = APIRouter()
deprecated_api_router.include_router(image_controller, prefix='/v1/image')
