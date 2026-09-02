"""Audit trail for data-plane row mutations made through the datasource API.

One row per (request, table). A single-table endpoint writes one row; the
multi-table endpoints write one per table, all sharing a ``batch_id`` — those
tables moved in one transaction, and the trail has to be able to say so.

Written best-effort and out-of-band against a *different* database from the one
that was mutated, so the two can never share a transaction. A missing row means
"the audit write lost", not "the mutation did not happen"; the reverse cannot
occur, because the audit is only ever written after the mutation commits.
"""

import uuid
from datetime import datetime

from sqlalchemy import Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class DatasourceAuditLog(Base):
    __tablename__ = 'datasource_audit_logs'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )

    # Groups the rows written by one HTTP request. Always set, even for the
    # single-table endpoints, so a consumer never has to special-case them.
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # No ForeignKey to datasource.id on purpose: delete_datasource hard-deletes
    # that row, and a FK would either cascade this trail away or block the
    # delete. An audit record has to outlive the thing it audits.
    datasource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Denormalized for the same reason there is no FK: once the datasource is
    # gone, this row is the only surviving record of what type it was.
    datasource_type: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        comment='possible values: postgres, gcp_bigquery, aws_redshift, mssql',
    )

    # Free-form, exactly as the caller supplied it (possibly 'schema.table').
    # Deliberately not an allowlist: the mutation endpoints do not run
    # check_is_valid_resource, so this table is the only record of a write to a
    # non-allowlisted table and must be able to name one.
    table_name: Mapped[str] = mapped_column(String(length=512), nullable=False)

    operation: Mapped[str] = mapped_column(
        String(length=16),
        nullable=False,
        comment='possible values: insert, update, delete',
    )

    # The OData filter as the caller wrote it, not the compiled SQL predicate:
    # the compiled form is an implementation detail of the parser, while the
    # OData string is what the caller can be held to. Null for inserts.
    #
    # 512 rather than something roomier because this column is indexed: a btree
    # entry caps at ~2704 bytes, and 512 chars of worst-case 4-byte UTF-8 is
    # 2048. The service truncates anything longer and flags it in `meta` — an
    # over-length filter must cost fidelity, never the whole audit row.
    filter: Mapped[str] = mapped_column(String(length=512), nullable=True)

    # The predicate reduced to its column -> value pairs, as the OData parser
    # produced them. Exists purely to make "which mutations targeted this column
    # with this value" a lookup rather than a substring scan over `filter`.
    #
    # Derived and deliberately redundant, never a replacement for `filter`: the
    # parser drops the comparison operator and the boolean structure, so
    # `x eq 1` and `x gt 1` reduce to the same pairs, as do `a $and b` and
    # `a $or b`. Only the string says what actually ran.
    filter_params: Mapped[dict] = mapped_column(JSONB, nullable=True)

    # {'snapshot': 'submitted'|'after'|'deleted', 'rows': [...]}. The bulky part,
    # and the part that carries customer data. Nullable so that "capture was not
    # available" stays distinguishable from "the mutation touched no rows".
    changes: Mapped[dict] = mapped_column(JSONB, nullable=True)

    # Small request context — requested patch, batch position, whether the call
    # spanned several tables. Never row data: that separation is what lets the
    # list endpoint return `meta` while omitting `changes`.
    meta: Mapped[dict] = mapped_column(JSONB, nullable=True)

    # cursor.rowcount — what the statement really touched, which is not
    # necessarily how many rows ended up in `changes`.
    rows_affected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # String, never UUID: the service-auth paths put literal non-UUID identities
    # on the session ('service', 'hmac-service', 'passthrough',
    # 'floconsole-service'), and a uuid column would reject every one of them.
    user_id: Mapped[str] = mapped_column(String(length=255), nullable=False)
    role_id: Mapped[str] = mapped_column(String(length=255), nullable=False)

    # X-Flo-Request-ID, for correlating against the application logs.
    request_id: Mapped[str] = mapped_column(String(length=64), nullable=True)

    # Set by the service at mutation time rather than left to func.now(): the
    # write happens on a background task that may run well after the mutation
    # committed, and a trail timestamped by write time cannot be ordered against
    # anything. The server default is a backstop only.
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=func.now())

    # Composites are (selective_col, created_at) so one scan serves both the
    # equality filter and the ORDER BY created_at DESC that every listing uses —
    # btree scans backwards, so an ASC index serves a DESC sort.
    #
    # `operation` and `datasource_type` are filterable but not indexed: 3-4
    # distinct values each, so Postgres would not choose a btree over a
    # created_at scan and the write cost would buy nothing.
    __table_args__ = (
        Index(
            'ix_datasource_audit_logs_datasource_created',
            'datasource_id',
            'created_at',
        ),
        Index('ix_datasource_audit_logs_table_created', 'table_name', 'created_at'),
        Index('ix_datasource_audit_logs_user_created', 'user_id', 'created_at'),
        # Plain btree: serves exact match and left-anchored prefix. A
        # "which mutations mention Q-1" substring search needs a GIN trigram
        # index (pg_trgm) instead, which is why the read API exposes no
        # contains filter today.
        Index('ix_datasource_audit_logs_filter', 'filter'),
    )

    @staticmethod
    def get_table_name():
        return DatasourceAuditLog.__tablename__

    def to_dict(self, include_changes: bool = False):
        """Serialize for the read API.

        ``changes`` is opt-in: it is unbounded and carries customer row data, so
        a listing that returned it would be both enormous and needlessly
        wide-reaching. The detail route asks for it explicitly.
        """
        result = {
            'id': str(self.id),
            'batch_id': str(self.batch_id),
            'datasource_id': str(self.datasource_id),
            'datasource_type': self.datasource_type,
            'table_name': self.table_name,
            'operation': self.operation,
            'filter': self.filter,
            'filter_params': self.filter_params,
            'meta': self.meta,
            'rows_affected': self.rows_affected,
            'user_id': self.user_id,
            'role_id': self.role_id,
            'request_id': self.request_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_changes:
            result['changes'] = self.changes
        return result
