from datetime import datetime
import uuid
import json

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from ..database.base import Base


class ModelSchema(Base):
    __tablename__ = 'model_inference'

    model_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    model_name: Mapped[str] = mapped_column(nullable=True, unique=True)
    model_path: Mapped[str] = mapped_column(nullable=True)
    model_type: Mapped[str] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    def to_dict(self):
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, uuid.UUID):
                result[column.name] = str(value)
            elif isinstance(value, datetime):
                result[column.name] = value.isoformat()
            elif column.name == 'meta':
                result[column.name] = json.loads(value) if value else None
            else:
                result[column.name] = value
        return result
