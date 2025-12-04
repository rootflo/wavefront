from sqlalchemy import Column, DateTime, func
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from ..database.base import Base


class ProductAnalytics(Base):
    __tablename__ = 'product_analytics'
    event_id = Column(UUID, primary_key=True, default=uuid.uuid4)
    event_name = Column(String, nullable=False)
    type = Column(String, nullable=True)
    sub_type = Column(String, nullable=True)
    category = Column(String, nullable=True)
    sub_category = Column(String, nullable=True)
    action = Column(String, nullable=True)
    action_type = Column(String, nullable=True)
    page = Column(String, nullable=False)
    page_path = Column(String, nullable=False)
    matadata = Column(JSONB, nullable=True)
    user_id = Column(UUID, nullable=False)
    session_id = Column(UUID, nullable=False)
    user_role = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    def to_dict(self):
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, uuid.UUID):
                result[column.name] = str(value)
            elif isinstance(value, datetime):
                result[column.name] = value.isoformat()
            else:
                result[column.name] = value
        return result

    @staticmethod
    def get_table_name():
        return (ProductAnalytics()).__tablename__
