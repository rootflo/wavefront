from datetime import datetime

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from ..database.base import Base


class Email(Base):
    __tablename__ = 'email'

    id: Mapped[str] = mapped_column(primary_key=True, index=True)
    thread_id: Mapped[str]
    account_id: Mapped[str]
    content: Mapped[str]
    synced_at: Mapped[datetime] = mapped_column(default=datetime.now)
