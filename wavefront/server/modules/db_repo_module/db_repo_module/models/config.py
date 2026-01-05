from ..database.base import Base
from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB


class Config(Base):
    __tablename__ = 'config'
    key = Column(String(255), primary_key=True)
    value = Column(JSONB, nullable=False)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now()
    )

    def to_dict(self):
        return {
            'key': self.key,
            'value': self.value,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    @staticmethod
    def get_table_name():
        return Config.__tablename__
