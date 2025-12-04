from typing import Any

from common_module.models.response import Meta
from common_module.models.response import ResponseModel


class ResponseFormatter:
    def buildSuccessResponse(self, data: Any):
        meta = Meta(status='success', code=1)
        if hasattr(data, 'dict'):
            data = data.dict()
        return ResponseModel(meta=meta, data=data).model_dump()

    def buildErrorResponse(self, error: str):
        meta = Meta(status='failure', code=-1, error=error)
        return ResponseModel(meta=meta).model_dump()
