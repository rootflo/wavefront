from db_repo_module.models.notification_users import NotificationUser
from db_repo_module.models.notifications import Notification
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository

# Every notification is visible to every user; `seen` is the only per-user state,
# and it lives in notification_user. The LEFT JOIN is what makes a row a user has
# never seen come back with seen NULL rather than not come back at all.
_JOIN = """
    FROM notification n
    LEFT JOIN notification_user nu
      ON n.id = nu.notification_id AND nu.user_id = :user_id
"""

# In the WHERE, not the ON: in the ON it would filter the joined side only,
# leaving every row present with its seen value blanked instead of excluded.
_UNSEEN_PREDICATE = 'WHERE (nu.seen IS NULL OR nu.seen = false)'


class NotificationService:
    def __init__(
        self,
        notification_repository: SQLAlchemyRepository[Notification],
        notification_user_repository: SQLAlchemyRepository[NotificationUser],
    ):
        self.notification_repository = notification_repository
        self.notification_user_repository = notification_user_repository

    async def fetch_notification(
        self, user_id, limit: int = 50, offset: int = 0, unseen_only: bool = False
    ):
        where = _UNSEEN_PREDICATE if unseen_only else ''
        query = f"""
                SELECT n.id as notification_id,
                n.type,
                n.title,
                n.data,
                n.created_at,
                n.updated_at,
                nu.user_id,
                nu.seen
                {_JOIN}
                {where}
                ORDER BY n.created_at DESC, n.id DESC
                LIMIT :limit OFFSET :offset
            """
        result = await self.notification_repository.execute_query(
            query, params={'user_id': user_id, 'limit': limit, 'offset': offset}
        )
        return result

    async def count_notifications(self, user_id, unseen_only: bool = False) -> int:
        """Total matching rows, for the paginated listing.

        Shares _JOIN and _UNSEEN_PREDICATE with fetch_notification so the count
        and the page can never disagree about what is being counted. The join is
        needed even here: `unseen_only` filters on the joined side.
        """
        where = _UNSEEN_PREDICATE if unseen_only else ''
        rows = await self.notification_repository.execute_query(
            f'SELECT COUNT(*) AS total {_JOIN} {where}',
            params={'user_id': user_id},
        )
        return rows[0]['total'] if rows else 0
