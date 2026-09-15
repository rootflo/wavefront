import uuid

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Index
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from ..database.base import Base


class Notification(Base):
    __tablename__ = 'notification'

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    title: String = Column(String, nullable=False)
    type: String = Column(String, nullable=False)
    # The structured payload behind `title`, which is only a denormalized
    # summary. Nullable because every row written before this column existed has
    # none, and because a producer is free to notify without a payload.
    data = Column(JSONB, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    notification_user = relationship('NotificationUser', back_populates='notification')

    # Matches the listing's ORDER BY exactly. The table went from effectively no
    # writes to one per datasource mutation, so the ordering can no longer be a
    # sort of everything.
    __table_args__ = (
        Index(
            'ix_notification_created_at',
            created_at.desc(),
            id.desc(),
        ),
    )

    @staticmethod
    def get_table_name():
        return (Notification()).__tablename__
