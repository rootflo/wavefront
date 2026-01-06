import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from ..base import Base


class App(Base):
    __tablename__ = 'app'

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    app_name: Mapped[str] = mapped_column(nullable=False)
    public_url: Mapped[str] = mapped_column(nullable=False)
    private_url: Mapped[str] = mapped_column(nullable=False)
    deleted: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(default='in_progress')
    config: Mapped[dict] = mapped_column(JSON, default={})
    deployment_type: Mapped[str] = mapped_column(nullable=False, default='manual')
    type: Mapped[str] = mapped_column(nullable=False, default='custom')
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True, default=datetime.now
    )

    # Add relationship for app access
    app_users = relationship(
        'AppUser', back_populates='app', cascade='all, delete-orphan'
    )

    def to_dict(self):
        return {
            'id': str(self.id),
            'app_name': self.app_name,
            'public_url': self.public_url,
            'private_url': self.private_url,
            'status': self.status,
            'config': self.config,
            'deployment_type': self.deployment_type,
            'type': self.type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
