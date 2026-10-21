from fastapi import APIRouter
from fastapi.responses import JSONResponse

from inference_app.di import application_container
from inference_app.models.mock import use_mock_models

# Separate from inference_app_router so health is never rate-limited.
health_router = APIRouter()


@health_router.get('/v1/health')
async def health_check():
    mock_models = use_mock_models(
        application_container.config()['models']['mock_models']
    )
    return JSONResponse(
        content={'status': 'ok', 'mock_models': mock_models},
        status_code=200,
    )
