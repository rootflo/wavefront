from db_repo_module.models.notification_users import NotificationUser
from db_repo_module.models.notifications import Notification
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository


class NotificationService:
    def __init__(
        self,
        notification_repository: SQLAlchemyRepository[Notification],
        notification_user_repository: SQLAlchemyRepository[NotificationUser],
    ):
        self.notification_repository = notification_repository
        self.notification_user_repository = notification_user_repository

    async def fetch_notification(self, user_id):
        query = """
                SELECT n.id as notification_id,
                n.type,
                n.title,
                n.created_at,
                n.updated_at,
                nu.user_id,
                nu.seen
                FROM notification n LEFT JOIN notification_user nu ON n.id = nu.notification_id
                AND nu.user_id = :user_id
                ORDER BY n.updated_at DESC
            """
        result = await self.notification_repository.execute_query(
            query, params={'user_id': user_id}
        )
        return result
