from fastapi.routing import APIRouter
from gold_module.controllers.image_controller import image_controller

gold_router = APIRouter()
gold_router.include_router(image_controller, prefix='/v1/image')
