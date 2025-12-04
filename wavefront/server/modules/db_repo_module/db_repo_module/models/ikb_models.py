from datetime import datetime
from sqlalchemy import (
    String,
    Integer,
    DateTime,
    Text,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db_repo_module.database.base import Base


class ImageKnowledgeBase(Base):
    """Image Knowledge Base - holds metadata about each IKB"""

    __tablename__ = 'image_knowledge_bases'

    ikb_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    ikb_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # gold_matching, photo_matching, etc.
    algorithm_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # sift, sam_dinov2, etc.
    status: Mapped[str] = mapped_column(
        String(20), default='active'
    )  # active, inactive
    config: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # Algorithm-specific configuration
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationship to reference images
    reference_images = relationship('ReferenceImageFeatures', back_populates='ikb')
