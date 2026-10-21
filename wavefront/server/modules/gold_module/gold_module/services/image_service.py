import io
from typing import Any, Dict
import uuid
from datetime import datetime
import json

from common_module.log.logger import logger
from common_module.utils.image_formats import SUPPORTED_PILLOW_FORMATS
from flo_cloud._types import MessageQueue
from flo_cloud.cloud_storage import CloudStorageManager
from PIL import Image


class ImageService:
    def __init__(
        self,
        bucket_name: str,
        cloud_storage_manager: CloudStorageManager,
        message_queue: MessageQueue,
    ):
        if not bucket_name:
            raise ValueError('application bucket name must be provided')
        self.bucket_name = bucket_name
        self.cloud_storage_manager = cloud_storage_manager
        self.message_queue = message_queue

    async def save_image(self, image_data: bytes, image_name: str):
        validated_image_data = await self._validate_image(image_data)
        self._upload(
            validated_image_data, f'historical_data/{image_name}', 'image/jpeg'
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

            self._upload(validated_image_data, object_key, 'image/jpeg')

            message = {
                'parse_type': 'gold',
                'bucket_name': self.bucket_name,
                'key': object_key,
                'metadata': self._custom_serializer(metadata),
            }

            self._upload(
                json.dumps(message).encode('utf-8'),
                f'gold_image_metadata/{object_key}.json',
                'application/json',
            )

            message_id = self.message_queue.add_message(message)
            logger.info(f'Successfully sent message to gold queue: {message_id}')

            return {
                'status': 'success',
                'message_id': message_id,
            }

        except Exception as e:
            logger.error(f'Error processing image: {str(e)}')
            raise Exception(f'Failed to process image: {str(e)}')

    def _upload(self, data: bytes, object_key: str, content_type: str) -> None:
        self.cloud_storage_manager.save_small_file(
            data,
            self.bucket_name,
            object_key,
            content_type=content_type,
        )

    async def _validate_image(self, image_data: bytes) -> bytes:
        try:
            with Image.open(
                io.BytesIO(image_data), formats=SUPPORTED_PILLOW_FORMATS
            ) as img:
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
