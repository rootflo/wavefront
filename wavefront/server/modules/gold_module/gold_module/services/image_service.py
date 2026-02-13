import io
from typing import Any, Dict
import uuid
from datetime import datetime
import json

from common_module.log.logger import logger
from gold_module.services.cloud_image_service import CloudImageService
from PIL import Image


class ImageService:
    def __init__(self, cloud_service: CloudImageService):
        self.cloud_service = cloud_service

    async def save_image(self, image_data: bytes, image_name: str):
        validated_image_data = await self._validate_image(image_data)

        bucket_name, file_path = await self.cloud_service.upload_image(
            validated_image_data, f'historical_data/{image_name}'
        )

    async def process_image(
        self, image_data: bytes, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            validated_image_data = await self._validate_image(image_data)
            object_key = metadata.get('item_id')
            if object_key is None or object_key == '':
                object_key = str(uuid.uuid4())
                metadata['item_id'] = object_key

            bucket_name, file_path = await self.cloud_service.upload_image(
                validated_image_data, object_key
            )

            message = {
                'parse_type': 'gold',
                'bucket_name': bucket_name,
                'key': file_path,
                'metadata': self._custom_serializer(metadata),
            }

            await self.cloud_service.upload_image_metadata(
                image_metadata=json.dumps(message),
                object_key=f'gold_image_metadata/{object_key}.json',
            )

            message_id = await self.cloud_service.send_message(message)

            return {
                'status': 'success',
                'message_id': message_id,
            }

        except Exception as e:
            logger.error(f'Error processing image: {str(e)}')
            raise Exception(f'Failed to process image: {str(e)}')

    async def _validate_image(self, image_data: bytes) -> bytes:
        try:
            with Image.open(io.BytesIO(image_data)) as img:
                # Ensure the image is in RGB format
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                buffer = io.BytesIO()
                img_format = img.format if img.format else 'JPEG'
                img.save(buffer, format=img_format, quality=85)
                return buffer.getvalue()
        except Exception as e:
            logger.error(f'Error validating image: {str(e)}')
            raise ValueError(f'Invalid image data: {str(e)}')

    def _custom_serializer(self, obj):
        """Helper method for JSON serialization"""
        if obj is None:
            return None
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: self._custom_serializer(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._custom_serializer(item) for item in obj]
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        return str(obj)
