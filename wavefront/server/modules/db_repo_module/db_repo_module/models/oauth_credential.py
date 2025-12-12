from typing import List

from sqlalchemy import JSON
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from ..database.base import Base


class OAuthCredential(Base):
    __tablename__ = 'oauth_credential'

    id: Mapped[str] = mapped_column(index=True, primary_key=True)
    email: Mapped[str]
    provider: Mapped[str]  # eg: google/azure
    access_token: Mapped[str]
    refresh_token: Mapped[str]
    token_uri: Mapped[str] = mapped_column(nullable=True)
    client_id: Mapped[str] = mapped_column(nullable=True)
    client_secret: Mapped[str] = mapped_column(nullable=True)
    scopes: Mapped[List[str]] = mapped_column(JSON)
    expiry: Mapped[int] = mapped_column(nullable=True)
