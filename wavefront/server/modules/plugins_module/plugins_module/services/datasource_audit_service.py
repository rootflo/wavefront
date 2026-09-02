"""Records data-plane row mutations made through the datasource API.

The mutation lands in the *customer's* datasource (psycopg2, synchronous, reached
via ``asyncio.to_thread``); the audit row lands in the *application* database
(SQLAlchemy async). Two servers, two drivers, two transactions — they cannot be
made atomic, so this service is best-effort by contract:

* it is only ever called after the mutation has already committed, so an audit
  row can never claim a change that did not happen;
* it never raises, so a failure here cannot turn a successful 200 into a 500;
* consequently "no audit row" means "the audit write lost", not "no mutation".

Writes happen on a background task so the caller's response is not held up by a
second database round trip.
"""

import asyncio
import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from common_module.log.logger import logger
from common_module.middleware.request_id_middleware import get_current_request_id
from common_module.utils.serializer import serialize_values
from db_repo_module.models.datasource_audit_log import DatasourceAuditLog
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from user_management_module.utils.user_utils import get_current_user

# Bounds on how much of a mutation is stored. Either can be set to None to lift
# that limit entirely; `rows_affected` is taken from cursor.rowcount and is never
# capped, so the true scale of a change survives whatever gets dropped here.
#
# The two limits catch different shapes, and the audited schemas are the
# caller's, so both are reachable. A delete matching thousands of narrow join
# rows is bounded by the row count; a handful of rows from a wide table, where a
# single row of jsonb columns runs to several KB, is bounded by bytes. Neither
# alone is enough.
AUDIT_MAX_ROWS: Optional[int] = 20
AUDIT_MAX_PAYLOAD_BYTES: Optional[int] = 256 * 1024  # 256 KiB of serialized rows

# Matches the `filter` column width. The column is indexed, and a btree entry
# caps at ~2704 bytes, so the column cannot simply be widened without dropping
# that index.
AUDIT_FILTER_MAX_CHARS = 512

# Held module-level: asyncio.create_task keeps only a weak reference to the task,
# so one with no other referent can be garbage collected mid-await and vanish
# silently. Keeping a strong reference until it finishes is the documented fix.
_pending_audit_tasks: set = set()


@dataclass(frozen=True)
class AuditEntry:
    """One table's worth of an audited mutation.

    ``rows`` distinguishes three states that must not be conflated: a list of
    rows, ``[]`` (captured, and the statement matched nothing), and ``None``
    (no capture was available — a datasource type with no RETURNING path).
    """

    table_name: str
    snapshot: str  # submitted | after | deleted
    rows: Optional[List[Dict[str, Any]]]
    rows_affected: int
    # The same rows as they were before an update. Present only on the update
    # paths, and None when the capture was unavailable or failed — in which case
    # the record degrades to an after-only snapshot rather than losing anything.
    before_rows: Optional[List[Dict[str, Any]]] = None
    # The table's primary key, present in both row sets so they can be paired.
    key_columns: Optional[List[str]] = None
    filter: Optional[str] = None  # OData, as the caller wrote it
    # The predicate's column -> value pairs. A derived search key, not a
    # substitute for `filter`: the parser drops operators and boolean structure.
    filter_params: Optional[Dict[str, Any]] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    # Set when the datasource client already stopped short of fetching every
    # affected row. Without it a client-side cap is invisible here: the rows that
    # arrive are exactly at the limit rather than over it, so nothing downstream
    # would notice that more existed.
    truncated: bool = False


@dataclass(frozen=True)
class AuditActor:
    """Who made the change.

    All strings, never UUIDs: the service-auth paths put literals like
    'hmac-service' on the session, and typing these as UUID would fail the insert
    for exactly the traffic that is hardest to attribute.
    """

    user_id: str
    role_id: str
    request_id: Optional[str]


def _log_audit_task_result(task: asyncio.Task) -> None:
    """Surface an exception from a fire-and-forget task.

    Nothing awaits these, so without this the traceback appears only as a
    "task exception was never retrieved" warning at interpreter shutdown, if at
    all.
    """
    if task.cancelled():
        return
    exception = task.exception()
    if exception is not None:
        logger.error(f'Datasource audit write failed: {exception}')


class DatasourceAuditService:
    def __init__(
        self,
        audit_log_repository: SQLAlchemyRepository[DatasourceAuditLog],
        max_rows: Optional[int] = AUDIT_MAX_ROWS,
        max_payload_bytes: Optional[int] = AUDIT_MAX_PAYLOAD_BYTES,
    ) -> None:
        self.audit_log_repository = audit_log_repository
        self.max_rows = max_rows
        self.max_payload_bytes = max_payload_bytes

    @property
    def capture_limit(self) -> Optional[int]:
        """How many rows the datasource client should be asked to return.

        Controllers read this rather than importing a constant, so the component
        that owns the storage decides how much of it to ask for. ``None`` means
        no limit.
        """
        return self.max_rows

    def record_from_request(
        self,
        request,
        *,
        datasource_id: str,
        datasource_type: str,
        operation: str,
        entries: Sequence[AuditEntry],
    ) -> None:
        """Schedule an audit write for a mutation that has already succeeded.

        Synchronous and returns immediately: identity is read here, on the
        request's own task, because ``request.state`` is torn down once the
        response is sent. Everything else happens on a background task.

        Does not raise, so callers can put it on a success path unwrapped.
        """
        try:
            # get_current_user returns (role_id, user_id, session_id) — that
            # order reads backwards, so unpack into named locals and pass by
            # keyword, which makes a transposition visible at review.
            role_id, user_id, _session_id = get_current_user(request)
            actor = AuditActor(
                user_id=user_id,
                role_id=role_id,
                request_id=get_current_request_id(),
            )
            # The mutation committed now; the row may be written seconds later,
            # and a trail timestamped by write time cannot be ordered against
            # anything else.
            occurred_at = datetime.now(timezone.utc).replace(tzinfo=None)
            self._spawn(
                self.record(
                    datasource_id=datasource_id,
                    datasource_type=datasource_type,
                    operation=operation,
                    entries=entries,
                    actor=actor,
                    occurred_at=occurred_at,
                )
            )
        except Exception:
            # Best-effort by contract: this runs on the success path of a
            # mutation that already committed, so nothing it can go wrong at may
            # turn a 200 into a 500.
            logger.error('Failed to schedule datasource audit write')

    async def record(
        self,
        *,
        datasource_id: str,
        datasource_type: str,
        operation: str,
        entries: Sequence[AuditEntry],
        actor: AuditActor,
        occurred_at: datetime,
        batch_id: Optional[uuid.UUID] = None,
    ) -> None:
        """Write the audit rows. Awaitable, for tests and any blocking caller."""
        try:
            # A statement that matched nothing is a success but not a change,
            # and this table records changes. Filtering here rather than at the
            # five call sites keeps the rule in one place — it matters on the
            # multi-table path, where require_all_matched=False lets some
            # entries match and others not.
            recordable = [entry for entry in entries if entry.rows_affected > 0]
            if not recordable:
                return

            batch_id = batch_id or uuid.uuid4()
            records = [
                self._build_record(
                    entry=entry,
                    batch_id=batch_id,
                    datasource_id=datasource_id,
                    datasource_type=datasource_type,
                    operation=operation,
                    actor=actor,
                    occurred_at=occurred_at,
                )
                for entry in recordable
            ]

            # create_all opens one session and commits once, so a multi-table
            # request's audit rows land together or not at all — matching the
            # atomicity of the mutation they describe. create() would open one
            # session per row and could half-succeed.
            await self.audit_log_repository.create_all(records)
        except Exception as e:
            logger.error(f'Failed to write datasource audit rows: {e}')

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        _pending_audit_tasks.add(task)
        task.add_done_callback(_pending_audit_tasks.discard)
        task.add_done_callback(_log_audit_task_result)

    def _build_record(
        self,
        *,
        entry: AuditEntry,
        batch_id: uuid.UUID,
        datasource_id: str,
        datasource_type: str,
        operation: str,
        actor: AuditActor,
        occurred_at: datetime,
    ) -> DatasourceAuditLog:
        changes, truncation_reason = self._build_changes(entry)
        audit_filter, filter_truncated = self._clip_filter(entry.filter)

        meta = dict(entry.meta)
        if truncation_reason:
            meta['truncation_reason'] = truncation_reason
        if filter_truncated:
            meta['filter_truncated'] = True
        # Only meaningful for updates: an insert has no prior state and a
        # delete's rows already are one, so their missing before is not a gap.
        # Recorded so a consumer can tell "this update has no diff because the
        # read failed" from "diffs are not a thing here".
        if entry.snapshot == 'after' and entry.before_rows is None:
            meta['before_capture'] = 'unavailable'

        return DatasourceAuditLog(
            batch_id=batch_id,
            # Coerced rather than passed through as the path-param string: the
            # column is uuid, and relying on the driver to infer a text->uuid
            # cast would make a malformed id fail inside the background task,
            # where the only symptom is a log line.
            datasource_id=uuid.UUID(str(datasource_id)),
            datasource_type=datasource_type,
            table_name=entry.table_name,
            operation=operation,
            filter=audit_filter,
            # Through the same normaliser as the row payload: an `in` filter
            # binds a list, and a numeric comparison binds a Decimal on some
            # paths, neither of which a jsonb column takes as-is.
            filter_params=serialize_values(entry.filter_params)
            if entry.filter_params
            else None,
            changes=changes,
            meta=meta or None,
            rows_affected=entry.rows_affected,
            user_id=actor.user_id,
            role_id=actor.role_id,
            request_id=actor.request_id,
            created_at=occurred_at,
        )

    @staticmethod
    def _clip_filter(value: Optional[str]) -> Tuple[Optional[str], bool]:
        """Fit the filter into the column, reporting whether it had to be cut.

        The column is VARCHAR(512) and would reject a longer value outright,
        failing the whole insert. An over-length filter has to cost fidelity,
        never the audit row.
        """
        if value is None or len(value) <= AUDIT_FILTER_MAX_CHARS:
            return value, False
        return value[:AUDIT_FILTER_MAX_CHARS], True

    def _build_diff(self, entry: AuditEntry) -> Dict[str, Any]:
        """Pair each row's prior values against what it became.

        The two row sets come from separate statements, so they arrive in
        whatever order the planner produced. Pairing by primary key is what makes
        a multi-row update meaningful — positionally, row 3's old value could
        easily be attributed to row 1.

        ``correlated: false`` marks the cases where no key is usable and the
        pairing falls back to position. That is unambiguous for a single-row
        update, which is the overwhelmingly common shape, and the flag tells a
        consumer not to trust it beyond that.
        """
        before_rows = entry.before_rows or []
        after_rows = entry.rows or []
        declared_key = entry.key_columns or []

        # A key column that is itself being updated changes value, so the two
        # sides no longer share it: pairing on it would silently mismatch rows.
        # It stops being a key and becomes an ordinary changed column — which is
        # why `key` is emptied here rather than merely ignored, or the one column
        # that actually moved would be stripped out of before/after.
        correlated = bool(declared_key) and not any(
            column in (entry.meta or {}).get('patch', {}) for column in declared_key
        )
        key_columns = declared_key if correlated else []

        def _split(row):
            key = {c: row[c] for c in key_columns if c in row}
            values = {c: v for c, v in row.items() if c not in key_columns}
            return key, values

        def _key_of(key):
            return tuple(key.get(c) for c in key_columns)

        rows: List[Dict[str, Any]] = []
        if correlated:
            before_by_key = {}
            for row in before_rows:
                key, values = _split(row)
                before_by_key[_key_of(key)] = values
            for row in after_rows:
                key, values = _split(row)
                # None, not {}: a row can be updated without a captured prior
                # value when the pre-read was capped, and that is not the same
                # as having had no values.
                rows.append(
                    {
                        'key': key,
                        'before': before_by_key.get(_key_of(key)),
                        'after': values,
                    }
                )
        else:
            for index, row in enumerate(after_rows):
                _, values = _split(row)
                before = before_rows[index] if index < len(before_rows) else None
                rows.append({'key': None, 'before': before, 'after': values})

        columns = sorted(
            {c for row in after_rows for c in row if c not in key_columns}
            or {c for row in before_rows for c in row if c not in key_columns}
        )

        return {
            'snapshot': 'diff',
            'columns': columns,
            'key_columns': key_columns or None,
            'correlated': correlated,
            'rows': rows,
        }

    def _build_changes(
        self, entry: AuditEntry
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Build the `changes` document, applying whatever caps are configured."""
        if entry.rows is None:
            # No capture was available. A null `changes` says exactly that; an
            # empty rows list would instead claim the mutation touched nothing.
            return None, 'capture_unavailable'

        # An update with a prior read becomes a diff; everything else keeps its
        # own snapshot shape. When the before-capture failed this falls through
        # to the after-only document rather than losing the record.
        if entry.snapshot == 'after' and entry.before_rows is not None:
            document = self._build_diff(entry)
        else:
            document = {'snapshot': entry.snapshot, 'rows': entry.rows}

        rows = document['rows']
        # A cap the client already applied counts as a row cap: it stopped
        # fetching for the same reason we would have stopped storing.
        reason: Optional[str] = 'row_cap' if entry.truncated else None

        if self.max_rows is not None and len(rows) > self.max_rows:
            rows = rows[: self.max_rows]
            reason = 'row_cap'

        rows = self._json_safe(rows)

        if self.max_payload_bytes is not None:
            # Halving rather than dropping one row at a time: measuring per row
            # is O(n) encodes of an already-large payload, this is O(log n).
            while rows and self._encoded_size(rows) > self.max_payload_bytes:
                rows = rows[: len(rows) // 2]
                reason = 'size_cap'
            if not rows and entry.rows:
                # Even a single row blew the cap. Storing a partially serialized
                # row would be worse than storing none — half a row reads as a
                # whole one.
                reason = 'row_exceeds_size_cap'

        document['rows'] = rows
        return document, reason

    @staticmethod
    def _encoded_size(rows: List[Dict[str, Any]]) -> int:
        return len(json.dumps(rows, separators=(',', ':')).encode('utf-8'))

    @classmethod
    def _json_safe(cls, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Reduce captured rows to values a jsonb column will accept.

        serialize_values is reused rather than reimplemented, but it covers only
        the common arrivals (UUID, date/datetime, Decimal, dict, list) — not
        bytea (bytes/memoryview), time, interval, inet or range types. The
        dumps/loads round trip with default=str catches those in one pass and
        normalises the result to primitives, so nothing exotic reaches the
        driver.

        Non-finite floats need separate handling, because a round trip does not
        remove them: json.dumps emits a bare ``NaN`` and json.loads parses it
        straight back into float('nan'), which Postgres jsonb then rejects,
        failing the whole insert. allow_nan=False turns that into a ValueError
        we can catch, and the retry stringifies them first.
        """
        pre = [serialize_values(row) for row in rows]
        try:
            return json.loads(json.dumps(pre, default=str, allow_nan=False))
        except ValueError:
            sanitized = [cls._replace_non_finite(row) for row in pre]
            return json.loads(json.dumps(sanitized, default=str, allow_nan=False))

    @classmethod
    def _replace_non_finite(cls, value: Any) -> Any:
        """Recursively replace NaN/Infinity with their string form.

        Only walked on the rare row that actually contains one — the common path
        never pays for this.
        """
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        if isinstance(value, dict):
            return {key: cls._replace_non_finite(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._replace_non_finite(item) for item in value]
        return value
