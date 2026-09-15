from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class GuardrailPolicy(Base):
    """Per-namespace AI guardrail policy.

    Scoped on `namespace` to match how agents and agentic configurations are
    organised. An earlier draft keyed this on `tenant_id`, a concept the schema
    does not otherwise have — the only `tenant_id` values in this codebase are
    Azure AD directory IDs on OAuth credentials, so a policy keyed that way
    could never have been joined to anything.

    One row per namespace, hence `namespace` as the primary key rather than a
    surrogate: there is no second policy to disambiguate.
    """

    __tablename__ = 'guardrail_policies'

    namespace: Mapped[str] = mapped_column(
        ForeignKey('namespaces.name'), primary_key=True
    )

    #: The master switch. When false the engine short-circuits and no safety
    #: provider is called at all, which is what makes this safe to leave
    #: configured but dormant.
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default='false'
    )

    #: MONITOR evaluates and records without enforcing; ENFORCE acts on the
    #: verdict. New policies start in MONITOR so a namespace can measure its
    #: false-positive rate against live traffic before anything can be blocked.
    mode: Mapped[str] = mapped_column(
        String(length=16), nullable=False, default='MONITOR', server_default='MONITOR'
    )

    #: Adapter set and per-adapter tuning, shaped for flo_ai's ResolvedPolicy:
    #: {"adapters": [{"name", "stages", "on_error", "timeout_seconds",
    #: "options"}]}. Credentials are never stored here - adapters are
    #: constructed from environment configuration.
    policy_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default='{}'
    )

    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    @staticmethod
    def get_table_name():
        return GuardrailPolicy.__tablename__

    def to_dict(self):
        return {
            'namespace': self.namespace,
            'is_enabled': self.is_enabled,
            'mode': self.mode,
            'policy_config': self.policy_config,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
