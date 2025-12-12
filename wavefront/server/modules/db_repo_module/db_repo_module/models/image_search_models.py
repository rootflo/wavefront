from datetime import datetime
import uuid
from sqlalchemy import (
    String,
    Float,
    Integer,
    DateTime,
    JSON,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db_repo_module.database.base import Base


# Base table for all reference images
class ReferenceImageFeatures(Base):
    __tablename__ = 'reference_image_features'

    reference_image_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    ikb_id: Mapped[str] = mapped_column(
        String(255), ForeignKey('image_knowledge_bases.ikb_id'), nullable=True
    )
    algorithm_type: Mapped[str] = mapped_column(String(50), nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    image_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationship to IKB
    ikb = relationship('ImageKnowledgeBase', back_populates='reference_images')


# SIFT-specific table (for 3000-5000 keypoints per image)
class SIFTFeatures(Base):
    __tablename__ = 'sift_features'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # reference_image_id: Mapped[str] = mapped_column(String(255), nullable=False)
    reference_image_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey('reference_image_features.reference_image_id', ondelete='CASCADE'),
        nullable=False,
    )
    keypoint_id: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # 0, 1, 2, ..., 4999

    # Keypoint properties
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    size: Mapped[float] = mapped_column(Float, nullable=False)
    angle: Mapped[float] = mapped_column(Float, nullable=False)
    response: Mapped[float] = mapped_column(Float, nullable=False)
    octave: Mapped[int] = mapped_column(Integer, nullable=False)
    class_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Descriptor (128 values as JSON array)
    descriptor: Mapped[list] = mapped_column(
        JSON, nullable=False
    )  # [0.12, 0.34, ..., 0.78]

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
