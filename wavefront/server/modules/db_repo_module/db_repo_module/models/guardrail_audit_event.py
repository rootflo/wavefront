import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class GuardrailAuditEvent(Base):
    """One durable record per guardrail decision.

    Most of why this feature exists is being able to answer "what did we block,
    for whom, and under which policy" months later. It is also the prerequisite
    for fail-open being a defensible posture rather than a silent one: an
    adapter outage downgrades to ALLOW, and without a record of the ERROR rate
    that is indistinguishable from traffic that was genuinely clean.

    Deliberately not keyed on `namespace` as a foreign key. Audit rows must
    outlive the things they describe — deleting a namespace must not delete the
    evidence of what happened in it — so the namespace is stored as a plain
    string.
    """

    __tablename__ = 'guardrail_audit_events'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    #: Plain string, not an FK: see the class docstring.
    namespace: Mapped[str] = mapped_column(String(length=255), nullable=False)
    agent_id: Mapped[Optional[str]] = mapped_column(String(length=255))
    user_id: Mapped[Optional[str]] = mapped_column(String(length=255))

    #: The platform request id, so a decision can be lined up with the
    #: application logs for the same call.
    run_id: Mapped[Optional[str]] = mapped_column(String(length=128))

    stage: Mapped[str] = mapped_column(String(length=32), nullable=False)

    #: What the policy did. In MONITOR this is always ALLOW.
    action: Mapped[str] = mapped_column(String(length=16), nullable=False)

    #: What it would have done. Populated in MONITOR too, and the whole point
    #: of monitor mode: measuring the would-be block rate before enforcing.
    observed_action: Mapped[str] = mapped_column(String(length=16), nullable=False)

    enforced: Mapped[bool] = mapped_column(Boolean, nullable=False)

    #: True when any adapter errored, whatever the final action. This is the
    #: column alerting watches: a rising rate here means checks are silently
    #: not running.
    had_error: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default='false'
    )

    policy_version: Mapped[Optional[str]] = mapped_column(String(length=64))

    #: Per-adapter verdicts: adapter, status, action, finding_code, severity,
    #: failure_class, and provider metadata such as PII entity counts.
    #:
    #: Never the evaluated content or the matched values. A guardrail exists to
    #: stop sensitive payloads spreading, and an audit table that copies them
    #: into a second, longer-lived store defeats the purpose.
    findings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default='[]'
    )

    created_at: Mapped[datetime] = mapped_column(default=func.now())

    __table_args__ = (
        # The two queries this table exists to serve: "what happened in this
        # namespace recently" and "is the error rate climbing".
        Index('ix_guardrail_audit_namespace_created', 'namespace', 'created_at'),
        Index('ix_guardrail_audit_had_error_created', 'had_error', 'created_at'),
    )

    @staticmethod
    def get_table_name():
        return GuardrailAuditEvent.__tablename__
