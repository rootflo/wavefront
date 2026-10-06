from fastapi import APIRouter
from fastapi.responses import JSONResponse

from inference_app.models import setup as models_setup

# Separate from inference_app_router so health is never rate-limited.
health_router = APIRouter()


@health_router.get('/v1/health')
async def health_check():
    return JSONResponse(
        content={'status': 'ok', 'mock_models': models_setup.MOCK_MODELS},
        status_code=200,
    )
