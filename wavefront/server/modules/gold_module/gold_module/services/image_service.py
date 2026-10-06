import io
import os
import uuid
from datetime import datetime
import json
from typing import Any, Dict, List

import httpx
from common_module.log.logger import logger
from common_module.utils.image_formats import SUPPORTED_PILLOW_FORMATS
from gold_module.services.cloud_image_service import CloudImageService
from gold_module.utils.segment_utils import (
    bytes_to_data_url,
    extract_image_bytes_from_contours,
)
from PIL import Image


class ImageService:
    def __init__(self, cloud_service: CloudImageService):
        self.cloud_service = cloud_service
        self.image_analysis_url = os.environ.get('IMAGE_ANALYSIS_URL')

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

    async def segment_image(
        self,
        image_data: bytes,
        segment_prompt: str = 'jewellery',
    ) -> Dict[str, Any]:
        """
        Run SAM segmentation via IMAGE_ANALYSIS_URL and return crop previews
        for the Fraud Search UI to pick from before KB retrieve.
        """
        if not self.image_analysis_url:
            raise ValueError('IMAGE_ANALYSIS_URL is not configured')

        validated = await self._validate_image(image_data)
        filename = 'fraud_search_segment.jpg'
        files = {'image': (filename, validated, 'image/jpeg')}
        data = {'segment_prompt': segment_prompt or 'jewellery'}

        logger.info(
            f'[image_segment] Calling IMAGE_ANALYSIS_URL={self.image_analysis_url}'
        )
        try:
            async with httpx.AsyncClient(timeout=240.0) as client:
                response = await client.post(
                    self.image_analysis_url,
                    files=files,
                    data=data,
                )
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f'[image_segment] Predict request failed: {e}', exc_info=True)
            raise Exception(f'Image segmentation service failed: {e}') from e

        prediction = response.json()
        raw_items = prediction.get('items') or []
        items: List[Dict[str, Any]] = []

        for item in raw_items:
            contours = item.get('contours')
            if not contours:
                continue
            if item.get('status') not in (None, 'success'):
                continue
            try:
                crop_bytes = extract_image_bytes_from_contours(
                    validated, contours, padding=0
                )
            except Exception as e:
                logger.warning(
                    f'[image_segment] Skipping item {item.get("item_index")}: {e}'
                )
                continue
            items.append(
                {
                    'index': item.get('item_index', len(items)),
                    'image': bytes_to_data_url(crop_bytes),
                    'predicted_category': item.get('predicted_category'),
                    'confidence_score': item.get('confidence_score'),
                }
            )

        logger.info(f'[image_segment] Returning {len(items)} segment crop(s)')
        return {
            'items': items,
            'total_items': len(items),
            'status': 'success' if items else 'no_items_detected',
        }

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
