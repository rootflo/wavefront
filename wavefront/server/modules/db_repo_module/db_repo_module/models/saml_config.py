from datetime import datetime
import uuid

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID

from ..database.base import Base


class BaseModel(Base):
    __abstract__ = True
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)

    def save(self, session):
        self.updated_at = datetime.now()
        session.add(self)
        session.commit()


class SAMLConfig(BaseModel):
    __tablename__ = 'saml_config'

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    entity_id = Column(String, nullable=False)
    sso_url = Column(String, nullable=False)
    slo_url = Column(String)
    x509_certificate = Column(String, nullable=False)
    name_id_format = Column(String)
    metadata_xml = Column(String)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True, index=True)
    created_by = Column(UUID)
