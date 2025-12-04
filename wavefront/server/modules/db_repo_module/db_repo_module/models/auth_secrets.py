import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from ..database.base import Base


class AuthSecrets(Base):
    __tablename__ = 'auth_secrets'

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    client_key: Mapped[str] = mapped_column(nullable=False, unique=True)
    client_secret: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=func.now(), onupdate=func.now()
    )

    def to_dict(self):
        return {
            'id': str(self.id),
            'client_key': self.client_key,
            'client_secret': self.client_secret,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }

    @staticmethod
    def get_table_name():
        return AuthSecrets().__tablename__
