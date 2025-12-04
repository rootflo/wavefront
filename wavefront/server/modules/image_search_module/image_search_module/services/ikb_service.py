from typing import List, Dict, Any, Optional
import uuid
import base64
import re
from datetime import datetime
from common_module.log.logger import logger

from image_search_module.models.ikb_models import (
    CreateIKBRequest,
    IKBInfo,
    IKBStatus,
    IKBType,
    IKBImageAddRequest,
    IKBSearchRequest,
    IKBSearchResponse,
)
from image_search_module.services.image_matching_service import ImageMatchingService
from image_search_module.services.reference_image_service import ReferenceImageService
from image_search_module.repositories.ikb_repository import IKBRepository


class IKBService:
    """Production-ready service for managing Image Knowledge Bases"""

    def __init__(
        self,
        image_matching_service: ImageMatchingService,
        reference_image_service: ReferenceImageService,
        ikb_repository: IKBRepository,
    ):
        self.image_matching_service = image_matching_service
        self.reference_image_service = reference_image_service
        self.ikb_repository = ikb_repository

    async def create_ikb(self, payload: CreateIKBRequest) -> IKBInfo:
        """Create a new Image Knowledge Base"""
        ikb_id = str(uuid.uuid4())

        ikb_info = IKBInfo(
            ikb_id=ikb_id,
            name=payload.name,
            description=payload.description,
            ikb_type=payload.ikb_type,
            algorithm_type=payload.algorithm_type,
            status=IKBStatus.ACTIVE,
            image_count=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            config=payload.config or {},
        )

        await self.ikb_repository.create_ikb(ikb_info)

        logger.info(f'Created new IKB: {ikb_info.name} (ID: {ikb_id})')
        return ikb_info

    async def get_ikb(self, ikb_id: str) -> Optional[IKBInfo]:
        """Get information about a specific IKB"""
        ikb_db = await self.ikb_repository.get_ikb(ikb_id)
        if not ikb_db:
            return None

        return self.ikb_repository._convert_to_ikb_info(ikb_db)

    async def list_ikbs(self, ikb_type: Optional[IKBType] = None) -> List[IKBInfo]:
        """List all IKBs, optionally filtered by type"""
        ikb_dbs = await self.ikb_repository.list_ikbs(ikb_type=ikb_type)

        return [self.ikb_repository._convert_to_ikb_info(ikb_db) for ikb_db in ikb_dbs]

    async def update_ikb(self, ikb_id: str, **updates) -> Optional[IKBInfo]:
        """Update an IKB"""
        ikb_db = await self.ikb_repository.update_ikb(ikb_id, **updates)
        if not ikb_db:
            return None

        logger.info(f'Updated IKB: {ikb_db.name} (ID: {ikb_id})')
        return self.ikb_repository._convert_to_ikb_info(ikb_db)

    async def delete_ikb(self, ikb_id: str) -> bool:
        """Delete an IKB"""
        success = await self.ikb_repository.delete_ikb(ikb_id)
        if success:
            logger.info(f'Deleted IKB (ID: {ikb_id})')
        return success

    async def add_image_to_ikb(
        self, ikb_id: str, payload: IKBImageAddRequest
    ) -> Dict[str, Any]:
        """add an image to a specific IKB"""
        ikb = await self.get_ikb(ikb_id)
        if not ikb:
            raise ValueError(f'IKB with ID {ikb_id} not found')

        if ikb.status != IKBStatus.ACTIVE:
            raise ValueError(f'IKB {ikb.name} is not active (status: {ikb.status})')

        # Decode base64 image
        data_url_pattern = r'^data:(image/\w+);base64,(.+)'
        match = re.match(data_url_pattern, payload.image_data)
        if not match:
            raise ValueError('Invalid image data format')

        image_bytes = base64.b64decode(match.group(2))

        # Generate reference ID if not provided
        reference_id = payload.reference_id or str(uuid.uuid4())

        # Add reference image with IKB ID
        result = await self.reference_image_service.add_reference_image(
            image_bytes=image_bytes,
            reference_image_id=reference_id,
            algorithm_type=ikb.algorithm_type.value,
            ikb_id=ikb_id,
            metadata={
                **payload.metadata,
                'ikb_id': ikb_id,
                'ikb_name': ikb.name,
                'ikb_type': ikb.ikb_type.value,
            },
        )

        # Update IKB image count in database
        await self.ikb_repository.increment_image_count(ikb_id)

        logger.info(f'added image to IKB {ikb.name}: {reference_id}')

        return {
            'reference_id': reference_id,
            'ikb_id': ikb_id,
            'ikb_name': ikb.name,
            'algorithm_type': ikb.algorithm_type.value,
            'extraction_results': result,
        }

    async def search_in_ikb(
        self, ikb_id: str, payload: IKBSearchRequest
    ) -> IKBSearchResponse:
        """Search for similar images within a specific IKB"""
        ikb = await self.get_ikb(ikb_id)
        if not ikb:
            raise ValueError(f'IKB with ID {ikb_id} not found')

        if ikb.status != IKBStatus.ACTIVE:
            raise ValueError(f'IKB {ikb.name} is not active (status: {ikb.status})')

        # Decode base64 image
        data_url_pattern = r'^data:(image/\w+);base64,(.+)'
        match = re.match(data_url_pattern, payload.image_data)
        if not match:
            raise ValueError('Invalid image data format')

        image_bytes = base64.b64decode(match.group(2))

        # Generate query ID
        query_id = str(uuid.uuid4())

        # Perform matching using the IKB's algorithm
        matching_result = await self.image_matching_service.match_image(
            image_bytes=image_bytes,
            ikb_id=ikb_id,
            max_results=payload.max_results,
            algorithm_type=ikb.algorithm_type,
        )

        # Filter results to only include images from this IKB
        ikb_matches = []
        for match in matching_result:
            # Get the reference image from database to check IKB ID
            reference_image = (
                await self.reference_image_service.features_repository.find_one(
                    reference_image_id=match.reference_id
                )
            )

            if reference_image and reference_image.ikb_id == ikb_id:
                ikb_matches.append(match.to_dict())

        response = IKBSearchResponse(
            query_id=query_id,
            ikb_id=ikb_id,
            ikb_name=ikb.name,
            algorithm_used=ikb.algorithm_type.value,
            matches=[match.to_dict() for match in matching_result],
            total_images_searched=ikb.image_count,
            processing_time_ms=sum(m.processing_time_ms for m in matching_result),
        )

        logger.info(f'Searched IKB {ikb.name}: found {len(ikb_matches)} matches')

        return response
