from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from enum import Enum

from image_search_module.algorithms.base import AlgorithmType


class IKBStatus(str, Enum):
    """Status of an Image Knowledge Base"""

    ACTIVE = 'active'
    INACTIVE = 'inactive'


class IKBType(str, Enum):
    """Types of Image Knowledge Bases"""

    GOLD_MATCHING = 'gold_matching'
    PHOTO_MATCHING = 'photo_matching'


class CreateIKBRequest(BaseModel):
    """Request to create a new Image Knowledge Base"""

    name: str = Field(..., description='Name of the IKB', min_length=1, max_length=100)
    description: Optional[str] = Field(
        None, description='Description of the IKB', max_length=500
    )
    ikb_type: IKBType = Field(..., description='Type of the IKB')
    algorithm_type: AlgorithmType = Field(
        ..., description='Algorithm to use for this IKB'
    )
    config: Dict[str, Any] = Field(
        default_factory=dict, description='Algorithm-specific configuration(required)'
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError('Name cannot be empty')
        return v.strip()


class IKBInfo(BaseModel):
    """Information about an Image Knowledge Base"""

    ikb_id: str = Field(..., description='Unique identifier for the IKB')
    name: str = Field(..., description='Name of the IKB')
    description: Optional[str] = Field(None, description='Description of the IKB')
    ikb_type: IKBType = Field(..., description='Type of the IKB')
    algorithm_type: AlgorithmType = Field(..., description='Algorithm used by this IKB')
    status: IKBStatus = Field(..., description='Current status of the IKB')
    image_count: int = Field(0, description='Number of images in this IKB')
    created_at: datetime = Field(..., description='When the IKB was created')
    updated_at: datetime = Field(..., description='When the IKB was last updated')
    config: Dict[str, Any] = Field(
        default_factory=dict, description='Algorithm-specific configuration'
    )


class IKBImageAddRequest(BaseModel):
    """Request to add an image to a specific IKB"""

    image_data: str = Field(..., description='Base64 encoded image data URL')
    reference_id: Optional[str] = Field(
        None, description='Custom reference ID (auto-generated if not provided)'
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description='Additional metadata for the image'
    )

    @field_validator('image_data')
    @classmethod
    def validate_image_data(cls, v):
        """Validate that image_data is a proper base64 data URL"""
        if not v.startswith('data:image/'):
            raise ValueError(
                'Image data must be a base64 data URL (data:image/...;base64,...)'
            )

        if ';base64,' not in v:
            raise ValueError('Image data must be base64 encoded')

        return v


class IKBSearchRequest(BaseModel):
    """Request to search within a specific IKB"""

    image_data: str = Field(..., description='Base64 encoded image data URL')
    max_results: int = Field(
        10, description='Maximum number of results to return', ge=1, le=100
    )
    threshold: Optional[float] = Field(None, description='Minimum similarity threshold')

    @field_validator('image_data')
    @classmethod
    def validate_image_data(cls, v):
        """Validate that image_data is a proper base64 data URL"""
        if not v.startswith('data:image/'):
            raise ValueError(
                'Image data must be a base64 data URL (data:image/...;base64,...)'
            )

        if ';base64,' not in v:
            raise ValueError('Image data must be base64 encoded')

        return v


class IKBSearchResponse(BaseModel):
    """Response from IKB search"""

    query_id: str = Field(..., description='Unique identifier for this search query')
    ikb_id: str = Field(..., description='ID of the IKB that was searched')
    ikb_name: str = Field(..., description='Name of the IKB that was searched')
    algorithm_used: str = Field(..., description='Algorithm used for matching')
    matches: List[Dict[str, Any]] = Field(..., description='List of matching results')
    total_images_searched: int = Field(
        ..., description='Total number of images in the IKB'
    )
    processing_time_ms: float = Field(
        ..., description='Total processing time in milliseconds'
    )
