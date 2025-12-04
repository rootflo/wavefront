import uuid

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database.base import Base


class Notification(Base):
    __tablename__ = 'notification'

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    title: String = Column(String, nullable=False)
    type: String = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    notification_user = relationship('NotificationUser', back_populates='notification')

    @staticmethod
    def get_table_name():
        return (Notification()).__tablename__
