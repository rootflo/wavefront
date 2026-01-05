from datetime import datetime, timezone
from typing import Optional, Tuple

from common_module.log.logger import logger
from db_repo_module.models.user import User
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository


class AccountInactivityService:
    def __init__(
        self, user_repository: SQLAlchemyRepository[User], inactive_days_threshold=60
    ):
        self.user_repository = user_repository
        self.inactive_days_threshold = (
            int(inactive_days_threshold) if inactive_days_threshold else 60
        )

    def _ensure_timezone_aware(self, dt: datetime) -> datetime:
        """Ensure datetime is timezone-aware (assumes UTC if naive)"""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    async def check_account_inactivity(self, user: User) -> Tuple[bool, Optional[int]]:
        """
        Check if user account should be disabled due to inactivity.
        Returns (should_be_disabled, days_since_last_login)
        """
        # If user has never logged in, allow login (first time users)
        if not user.last_login_at:
            logger.info(f'User {user.email} has never logged in, allowing first login')
            return False, None

        current_time = datetime.now(timezone.utc)
        last_login_aware = self._ensure_timezone_aware(user.last_login_at)
        time_diff = current_time - last_login_aware
        days_since_login_precise = time_diff.total_seconds() / (
            24 * 60 * 60
        )  # Fractional days for comparison
        days_since_login_display = int(days_since_login_precise)  # Integer for display

        is_inactive = days_since_login_precise > self.inactive_days_threshold

        if is_inactive:
            logger.warning(
                f'User {user.email} has been inactive for {days_since_login_display} days '
                f'(threshold: {self.inactive_days_threshold} days)'
            )

        return is_inactive, days_since_login_display

    async def update_last_login(self, user: User) -> None:
        """Update user's last login timestamp on successful authentication"""
        current_time = datetime.now(timezone.utc)

        await self.user_repository.find_one_and_update(
            {'id': user.id}, last_login_at=current_time
        )

        logger.info(f'Updated last login timestamp for user {user.email}')
