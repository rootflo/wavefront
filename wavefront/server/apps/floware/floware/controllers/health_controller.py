from authz_module import public_route
from fastapi import Depends
from fastapi import APIRouter
from fastapi.responses import JSONResponse

health_router = APIRouter()


@health_router.get('/v1/health', dependencies=[Depends(public_route)])
def health_check():
    return JSONResponse(content={'status': 'ok'}, status_code=200)
