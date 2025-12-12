import uuid

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import UUID
from sqlalchemy.orm import relationship

from ..database.base import Base


class NotificationUser(Base):
    __tablename__ = 'notification_user'

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID, ForeignKey('user.id'), nullable=False)
    notification_id = Column(UUID, ForeignKey('notification.id'), nullable=False)
    seen = Column(Boolean, nullable=False, default=False)

    notification = relationship('Notification', back_populates='notification_user')

    @staticmethod
    def get_table_name():
        return (NotificationUser()).__tablename__
