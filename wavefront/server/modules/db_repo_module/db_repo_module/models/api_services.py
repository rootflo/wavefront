from datetime import datetime

from sqlalchemy import Boolean, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class ApiServices(Base):
    __tablename__ = 'api_services'

    id: Mapped[str] = mapped_column(
        String(length=255), nullable=False, unique=True, primary_key=True
    )
    service_def_path: Mapped[str] = mapped_column(String(length=255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    @staticmethod
    def get_table_name():
        return (ApiServices()).__tablename__

    def to_dict(self):
        return {
            'id': self.id,
            'service_def_path': self.service_def_path,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
