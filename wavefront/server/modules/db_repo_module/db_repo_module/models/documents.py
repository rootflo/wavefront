from datetime import datetime

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from ..database.base import Base


class Document(Base):
    __tablename__ = 'document'

    document_id: Mapped[str] = mapped_column(primary_key=True, index=True)
    document_name: Mapped[str]
    last_update_timestamp: Mapped[datetime] = mapped_column(default=datetime.now)
