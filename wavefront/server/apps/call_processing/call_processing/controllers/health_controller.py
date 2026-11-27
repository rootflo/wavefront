from authz_module import public_route
from fastapi import Depends
from fastapi import APIRouter
from fastapi.responses import JSONResponse

health_router = APIRouter()


@health_router.get('/health', dependencies=[Depends(public_route)])
async def health_check():
    return JSONResponse(
        content={'status': 'healthy', 'service': 'call-processing'}, status_code=200
    )
