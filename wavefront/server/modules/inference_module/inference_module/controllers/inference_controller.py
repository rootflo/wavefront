from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from db_repo_module.models.model_schema import ModelSchema
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, File, Form, UploadFile, status, Query
from fastapi.responses import JSONResponse
from inference_module.inference_container import InferenceContainer
from flo_cloud.cloud_storage import CloudStorageManager
from db_repo_module.cache.cache_manager import CacheManager
from sqlalchemy import update, select, Result
import httpx
import uuid


inference_router = APIRouter()


@inference_router.post('/v1/model-repository/model')
@inject
async def model_loading(
    model_type: str = Form(..., description='The type of the model'),
    model_file: UploadFile = File(..., description='The model file to be uploaded'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    model_inference_repository: SQLAlchemyRepository[ModelSchema] = Depends(
        Provide[InferenceContainer.model_inference_repository]
    ),
    cloud_storage_manager: CloudStorageManager = Depends(
        Provide[InferenceContainer.cloud_storage_manager]
    ),
    config: InferenceContainer.config.provided = Depends(
        Provide[InferenceContainer.config]
    ),
    cache_manager: CacheManager = Depends(Provide[CommonContainer.cache_manager]),
):
    provider = config['cloud_config']['cloud_provider']
    model_storage_bucket = (
        config['gcp']['model_storage_bucket']
        if provider.lower() == 'gcp'
        else config['aws']['model_storage_bucket']
    )
    if cache_manager.get_str(f"model_name_key_{model_file.filename.split('.')[0]}"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Model details already found in the Model inference table'
            ),
        )
    else:
        cache_manager.add(
            f"model_name_key_{model_file.filename.split('.')[0]}",
            model_file.filename.split('.')[0],
            600,
        )
    filepath = f'inference/model/{model_file.filename}'
    async with model_inference_repository.session() as session:
        model_record = ModelSchema(
            model_name=model_file.filename.split('.')[0],
            model_path=filepath,
            model_type=model_type,
        )
        session.add(model_record)
        await session.flush()
        model_id = model_record.model_id
        filename = model_file.filename.replace(' ', '_')
        gcs_file_name = f'model_{model_id}/{filename}'
        file_content = await model_file.read()
        cloud_storage_manager.save_large_file(
            file_content,
            model_storage_bucket,
            gcs_file_name,
        )
        await session.commit()
        await session.execute(
            update(ModelSchema)
            .where(ModelSchema.model_id == model_id)
            .values(model_path=gcs_file_name)
        )
        await session.commit()
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Created the model inference table and inserted the model deails successfully',
                'model_id': str(model_id),
            }
        ),
    )


@inference_router.post('/v1/model-repository/model/{model_id}/infer')
@inject
async def redirect_model_inference_api(
    model_id: str,
    data: dict,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    config: InferenceContainer.config.provided = Depends(
        Provide[InferenceContainer.config]
    ),
    model_inference_repository: SQLAlchemyRepository[ModelSchema] = Depends(
        Provide[InferenceContainer.model_inference_repository]
    ),
):
    model_info = await model_inference_repository.find_one(model_id=model_id)
    if not model_info:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Model details not found in the Model inference table'
            ),
        )
    data['model_info'] = ModelSchema.to_dict(model_info)
    internal_api_url = f"{config['model']['inference_service_url']}/inference/v1/model-repository/model/{model_id}/infer"
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, connect=30.0),
        limits=httpx.Limits(
            max_keepalive_connections=20, max_connections=100, keepalive_expiry=60
        ),
    ) as client:
        response = await client.post(internal_api_url, json=data)

        # Log error if response status is not successful
        if response.status_code != 201:
            error_response_text = (
                response.text[:1000]
                if hasattr(response, 'text')
                else 'No response text available'
            )
            logger.error(
                f'Failed to call internal inference API. URL: {internal_api_url}, '
                f'Model ID: {model_id}, Status Code: {response.status_code}, '
                f'Error Response: {error_response_text}'
            )
            # Return error response when internal API fails
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f'Internal inference API returned error: {error_response_text}'
                ),
            )

        logger.debug(f'The response value is {response.json()}')
        response = response.json().get('data', {}).get('results', {})
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response_formatter.buildSuccessResponse({'data': response}),
        )


@inference_router.get('/v1/model-repository/model')
@inject
async def list_all_models(
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    limit: int = Query(
        10, ge=1, le=100, description='The maximum number of items to return'
    ),
    model_inference_repository: SQLAlchemyRepository[ModelSchema] = Depends(
        Provide[InferenceContainer.model_inference_repository]
    ),
):
    async with model_inference_repository.session() as session:
        query = select(ModelSchema).slice(0, limit)
        results: Result = await session.execute(query)
        resources = results.scalars().all()
        data = [res.to_dict() for res in resources]
    return JSONResponse(
        content=response_formatter.buildSuccessResponse({'data': data}),
        status_code=status.HTTP_200_OK,
    )


@inference_router.get('/v1/model-repository/model/{model_id}')
@inject
async def list_model_from_id(
    model_id: uuid.UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    model_inference_repository: SQLAlchemyRepository[ModelSchema] = Depends(
        Provide[InferenceContainer.model_inference_repository]
    ),
):
    model_info = await model_inference_repository.find_one(model_id=model_id)
    if not model_info:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Model details not found in the Model inference table'
            ),
        )
    return JSONResponse(
        content=response_formatter.buildSuccessResponse(
            {'data': ModelSchema.to_dict(model_info)}
        ),
        status_code=status.HTTP_200_OK,
    )


@inference_router.delete('/v1/model-repository/model/{model_id}')
@inject
async def delete_model_from_id(
    model_id: uuid.UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    model_inference_repository: SQLAlchemyRepository[ModelSchema] = Depends(
        Provide[InferenceContainer.model_inference_repository]
    ),
):
    model_info = await model_inference_repository.find_one(model_id=model_id)
    if not model_info:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Model details not found in the Model inference table'
            ),
        )
    await model_inference_repository.delete_all(model_id=model_id)
    return JSONResponse(
        status_code=status.HTTP_204_NO_CONTENT,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Deleted the Model Inference record successfully',
                'model_id': str(model_id),
            }
        ),
    )
