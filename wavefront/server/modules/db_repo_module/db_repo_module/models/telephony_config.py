import json
import uuid
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class TelephonyConfig(Base):
    __tablename__ = 'telephony_configs'

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, index=True
    )
    display_name: Mapped[str] = mapped_column(String(length=100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(
        String(length=500), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(length=64), nullable=False)
    connection_type: Mapped[str] = mapped_column(String(length=64), nullable=False)
    credentials: Mapped[str] = mapped_column(Text, nullable=False)
    webhook_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sip_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    @staticmethod
    def get_table_name():
        return (TelephonyConfig()).__tablename__

    def to_dict(self, secret_fields: Optional[Iterable[str]] = None):
        """Public form for API responses, with the secret credentials masked.

        `secret_fields` are the provider's secret credential keys; without them
        every credential value is masked.
        """
        return self.public_dict(self.to_stored_dict(), secret_fields)

    def to_stored_dict(self):
        """Every column as stored, so secret credentials are ciphertext when encryption is on."""
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, uuid.UUID):
                result[column.name] = str(value)
            elif isinstance(value, datetime):
                result[column.name] = value.isoformat()
            elif (
                column.name in ['credentials', 'webhook_config', 'sip_config'] and value
            ):
                # Parse JSON fields
                try:
                    result[column.name] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    result[column.name] = value
            else:
                result[column.name] = value
        return result

    @staticmethod
    def public_dict(
        stored: dict, secret_fields: Optional[Iterable[str]] = None
    ) -> dict:
        """Public form of a stored dict (e.g. one read back from the cache)."""
        # Imported here so loading the models does not pull in the crypto stack
        from common_module.security.secret_cipher import SECRET_MASK, SecretCipher

        result = dict(stored)
        credentials = result.get('credentials')
        if isinstance(credentials, dict):
            fields = credentials.keys() if secret_fields is None else secret_fields
            result['credentials'] = SecretCipher.mask_fields(credentials, fields)
        elif credentials:
            # Unparseable credentials cannot be masked field by field
            result['credentials'] = SECRET_MASK
        return result
