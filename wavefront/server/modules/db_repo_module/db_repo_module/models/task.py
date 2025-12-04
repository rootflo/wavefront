from datetime import datetime

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from ..database.base import Base


class Task(Base):
    __tablename__ = 'task'

    message_id: Mapped[str] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(nullable=False)
    account_id: Mapped[str] = mapped_column(nullable=False)
    sender: Mapped[str] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(nullable=False)
    priority: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
