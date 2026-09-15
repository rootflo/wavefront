"""Fans a recorded datasource mutation out to the notification feed.

Kept separate from DatasourceAuditService so that service stays about auditing,
but driven from it, so there is exactly one place that means "a change happened".

The two tables answer different questions and have different audiences.
``datasource_audit_logs`` is the record of truth, admin-gated by default, and
found only by querying it. ``notification`` is a feed every authenticated user
reads. Nothing here re-captures or re-computes anything: the payload is copied
off the DatasourceAuditLog rows the audit service already built, so the two can
never disagree about what changed, and the row/byte caps applied there are
inherited for free.

Best-effort in the same sense as the audit write, and one step further down the
chain: this runs after a mutation that has already committed *and* after an audit
row that has already landed, so it must never raise and never hold anything up.
"""

import json
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

from common_module.feature.feature_flag import (
    DATASOURCE_CHANGE_NOTIFICATION_FLAG,
    is_feature_enabled,
)
from common_module.log.logger import logger
from db_repo_module.models.datasource_audit_log import DatasourceAuditLog
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository

from plugins_module.services.datasource_audit_service import AuditActor

if TYPE_CHECKING:
    # Import-time only. Notification declares relationship('NotificationUser'),
    # which SQLAlchemy resolves by name at mapper-configuration time, so
    # importing this module without notification_users leaves the registry
    # unconfigurable and every later model instantiation raises. Nothing here
    # needs the class at runtime -- only the annotation does.
    from db_repo_module.models.notifications import Notification

# Consumers branch on this rather than parsing `title`.
NOTIFICATION_TYPE = 'datasource_change'

# Names the producer, so a future non-datasource notification can share the table
# without a consumer having to infer where a payload came from.
NOTIFICATION_SOURCE = 'datasource'

# (participle, preposition). Split rather than stored as one phrase because only
# the single-table title takes the preposition: a batch reads "updated across 2
# tables", never "updated in across 2 tables".
_VERBS = {
    'insert': ('inserted', 'into'),
    'update': ('updated', 'in'),
    'delete': ('deleted', 'from'),
}

# The table name is the caller's and its column allows 512 characters. The title
# column is an unbounded String, so this is about keeping a feed readable rather
# than about fitting the column.
TITLE_TABLE_MAX_CHARS = 64

# Deliberately larger than AUDIT_MAX_PAYLOAD_BYTES, which bounds *one table's*
# rows. Reusing that number here bounded the whole document by one table's
# budget, so a single table whose rows landed just under it -- legal, and kept in
# full by the audit row -- was pushed over by the envelope around it and had its
# `changes` dropped entirely. A batch carries several such tables, so the budget
# for the batch has to exceed the budget for a table.
NOTIFICATION_MAX_PAYLOAD_BYTES = 1024 * 1024  # 1 MiB


class ChangeNotificationService:
    def __init__(
        self,
        notification_repository: 'SQLAlchemyRepository[Notification]',
        max_payload_bytes: Optional[int] = NOTIFICATION_MAX_PAYLOAD_BYTES,
    ) -> None:
        self.notification_repository = notification_repository
        self.max_payload_bytes = max_payload_bytes

    def build_payload(
        self,
        *,
        datasource_id: str,
        datasource_type: str,
        operation: str,
        actor: AuditActor,
        occurred_at: datetime,
        batch_id: uuid.UUID,
        records: Sequence[DatasourceAuditLog],
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Build ``(title, data)`` for one mutating request, or None to skip.

        Pure, and deliberately separate from the write: it **must** be called
        before the audit rows are inserted. The session factory leaves
        ``expire_on_commit`` at its default, so once create_all commits and
        closes its session the records are expired *and* detached, and reading
        ``record.changes`` off one raises DetachedInstanceError. Building here
        means only a plain dict crosses the commit boundary.

        Returns None when the flag is off or there is nothing to report, which
        the caller reads as "do not publish".
        """
        if not is_feature_enabled(DATASOURCE_CHANGE_NOTIFICATION_FLAG):
            return None

        if not records:
            return None

        tables = [
            {
                'table_name': record.table_name,
                # From cursor.rowcount, and never capped -- the true scale of the
                # change survives whatever `changes` had to drop.
                'rows_affected': record.rows_affected,
                'filter': record.filter,
                'filter_params': record.filter_params,
                'meta': record.meta,
                'changes': record.changes,
            }
            for record in records
        ]

        total_rows = sum(record.rows_affected for record in records)

        data: Dict[str, Any] = {
            'source': NOTIFICATION_SOURCE,
            'batch_id': str(batch_id),
            'datasource_id': str(datasource_id),
            'datasource_type': datasource_type,
            'operation': operation,
            # The mutation's commit time, not this row's write time: the feed is
            # ordered against other events, and a write-time stamp cannot be.
            'occurred_at': occurred_at.isoformat() if occurred_at else None,
            'rows_affected': total_rows,
            'table_count': len(tables),
            'actor': {
                'user_id': actor.user_id,
                'role_id': actor.role_id,
                'request_id': actor.request_id,
            },
            'tables': tables,
        }

        self._apply_batch_cap(data)

        return self._build_title(operation, total_rows, tables), data

    async def publish(self, title: str, data: Dict[str, Any]) -> None:
        """Write the notification row. Never raises.

        A failure here costs a feed entry for a change that is already committed
        and already audited, which is not worth propagating anywhere.
        """
        try:
            await self.notification_repository.create(
                title=title,
                type=NOTIFICATION_TYPE,
                data=data,
            )
        except Exception as e:
            logger.error(f'Failed to write datasource change notification: {e}')

    def _apply_batch_cap(self, data: Dict[str, Any]) -> None:
        """Bound the whole document, not just each table's share of it.

        Every `changes` document arrives already capped, but those caps are per
        table and a batch multiplies them -- an N-table request can carry N times
        the per-table limit in a single jsonb value.

        `changes` is not the only thing that can overflow, though, and often is
        not the thing that did: `meta` carries `patch`, the submitted update
        payload, and the audit service does not cap it. A document can exceed
        the budget with every `changes` already empty, so dropping detail alone
        cannot enforce it.

        Trimming therefore escalates, shedding the least useful thing that is
        still large, and the size is re-checked after each step so the document
        is never published over budget:

        1. trailing tables lose `changes`, keeping their metadata, so the feed
           still reports that they changed and by how much;
        2. every table loses `meta` -- uncapped, and the one field that is safe
           to lose, since `patch` is the values that were set and
           `changes.after` already shows those;
        3. the leading table loses `changes`;
        4. the table list itself is halved.

        Step 3 comes late deliberately. It is the last thing a reader can still
        act on, and it is already bounded by the audit service's per-table cap,
        so shedding it before `meta` would trade real detail for nothing.

        `filter_params` is never dropped. It says which rows were targeted,
        which is identity rather than detail and is recoverable from nothing
        else here -- `filter` holds the same thing but is clipped to 512
        characters. It is uncapped, so a large enough predicate can hold a
        document above the budget on its own; step 4 is what bounds that, by
        removing whole entries rather than hollowing them out.
        """
        if self.max_payload_bytes is None:
            return

        tables = data['tables']

        def over_budget() -> bool:
            return self._encoded_size(data) > self.max_payload_bytes

        if not over_budget():
            return

        # 1. Back to front, so the entries a feed shows first are the last to
        #    lose their detail. Stops at 1; the leading table is step 3.
        for index in range(len(tables) - 1, 0, -1):
            if not over_budget():
                break
            if tables[index]['changes'] is None:
                continue
            tables[index]['changes'] = None

        # 2. `meta` only. It is uncapped, and `patch` -- the bulk of it on the
        #    update paths -- is the values that were set, which changes.after
        #    already shows. filter_params is uncapped too but is deliberately
        #    kept: it is which rows were touched, not what they became.
        if over_budget():
            for table in tables:
                table['meta'] = None
            data['metadata_dropped'] = True

        # 3. The leading table's detail, once there is nothing cheaper left.
        if over_budget() and tables and tables[0]['changes'] is not None:
            tables[0]['changes'] = None

        # 4. Only bare table names remain, so this needs a pathological number of
        #    tables in one request. Halved rather than popped one at a time: the
        #    same reasoning as the audit service's row trimming, O(log n) encodes
        #    of an already-large payload instead of O(n).
        while over_budget() and len(tables) > 1:
            removed = len(tables) - len(tables) // 2
            del tables[len(tables) // 2 :]
            data['tables_omitted'] = data.get('tables_omitted', 0) + removed

        # One canonical "this was trimmed" signal, whichever steps ran. The
        # specific flags above say what was lost.
        data['truncation_reason'] = 'batch_size_cap'

    @staticmethod
    def _encoded_size(document: Dict[str, Any]) -> int:
        return len(
            json.dumps(document, separators=(',', ':'), default=str).encode('utf-8')
        )

    @classmethod
    def _build_title(
        cls, operation: str, total_rows: int, tables: List[Dict[str, Any]]
    ) -> str:
        """A one-line summary. `data` stays authoritative.

        Denormalized on purpose: a feed should be renderable without unpacking
        the payload, and a client that wants to localize builds its own string.
        """
        noun = '1 row' if total_rows == 1 else f'{total_rows} rows'
        # An operation outside the known set still produces a usable title. This
        # runs on a best-effort path after a committed mutation, so a KeyError
        # here must not be what loses the notification.
        participle, preposition = _VERBS.get(
            operation, (f'changed ({operation})', 'in')
        )

        if len(tables) == 1:
            table = cls._clip_table(tables[0]['table_name'])
            return f'{noun} {participle} {preposition} {table}'

        return f'{noun} {participle} across {len(tables)} tables'

    @staticmethod
    def _clip_table(table_name: str) -> str:
        if table_name is None or len(table_name) <= TITLE_TABLE_MAX_CHARS:
            return table_name
        return f'{table_name[:TITLE_TABLE_MAX_CHARS]}…'
