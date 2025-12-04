from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator
import base64
import re


class ImageSearchRequest(BaseModel):
    """Request model for image search with base64 data URL"""

    image_data: str = Field(
        ..., description='Base64 encoded image data URL (data:image/...;base64,...)'
    )
    algorithm_type: Optional[str] = Field(
        None, description='Algorithm type to use (sift, sam_dinov2, custom_model)'
    )

    @validator('image_data')
    def validate_image_data(cls, v):
        """Validate that image_data is a proper base64 data URL"""
        if not v.startswith('data:image/'):
            raise ValueError(
                'Image data must be a base64 data URL (data:image/...;base64,...)'
            )

        if ';base64,' not in v:
            raise ValueError('Image data must be base64 encoded')

        # Extract and validate base64 data
        try:
            data_url_pattern = r'^data:(image/\w+);base64,(.+)'
            match = re.match(data_url_pattern, v)
            if not match:
                raise ValueError('Invalid data URL format')

            # Decode to check size and validity
            base64_data = match.group(2)
            image_bytes = base64.b64decode(base64_data)

            # Check size limit (20MB original = ~26.6MB base64)
            MAX_SIZE = 20 * 1024 * 1024  # 20MB
            if len(image_bytes) > MAX_SIZE:
                raise ValueError(
                    f'Image too large. Maximum size: {MAX_SIZE // (1024*1024)}MB'
                )

            return v

        except base64.binascii.Error:
            raise ValueError('Invalid base64 encoding')
        except Exception as e:
            raise ValueError(f'Invalid image data: {str(e)}')

    @validator('algorithm_type')
    def validate_algorithm_type(cls, v):
        """Validate algorithm type if provided"""
        if v is not None:
            valid_types = ['sift']
            if v not in valid_types:
                raise ValueError(
                    f'Invalid algorithm type. Must be one of: {valid_types}'
                )
        return v


class MatchResult(BaseModel):
    """Individual match result"""

    algorithm_type: str
    reference_id: str
    match_score: float
    is_match: bool
    confidence: float
    processing_time_ms: float
    metadata: Dict[str, Any]


class ImageSearchResponse(BaseModel):
    """Response model for image search"""

    query_id: str
    matches: List[MatchResult]
    algorithm_used: str
    processing_time_ms: float
