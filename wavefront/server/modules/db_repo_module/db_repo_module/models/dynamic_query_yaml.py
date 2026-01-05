from ..database.base import Base
from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship


class DynamicQueryYaml(Base):
    __tablename__ = 'dynamic_query_yaml'
    name = Column(String(255), primary_key=True)
    file_path = Column(String(255), nullable=False)
    datasource_id = Column(
        UUID, ForeignKey('datasource.id', ondelete='CASCADE'), nullable=False
    )
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now()
    )

    datasource = relationship('Datasource', back_populates='dynamic_queries')

    def to_dict(self):
        return {
            'name': self.name,
            'file_path': self.file_path,
            'datasource_id': str(self.datasource_id),
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    @staticmethod
    def get_table_name():
        return DynamicQueryYaml.__tablename__
