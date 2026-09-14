import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.user import User
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from user_management_module.constants.cache import user_by_id_cache_key

USER_CACHE_TTL_SECONDS = 60 * 60


class AccountLockoutService:
    def __init__(
        self,
        user_repository: SQLAlchemyRepository[User],
        cache_manager: CacheManager,
        max_failed_attempts=3,
        lockout_duration_hours=24,
    ):
        self.user_repository = user_repository
        self.cache_manager = cache_manager
        # Convert to int in case they come as strings from config
        self.max_failed_attempts = (
            int(max_failed_attempts) if max_failed_attempts else 3
        )
        self.lockout_duration_hours = (
            int(lockout_duration_hours) if lockout_duration_hours else 24
        )

    def _cache_user(self, user: User, expiry: int = USER_CACHE_TTL_SECONDS) -> None:
        """Write the user onto the same key GET /users/{id} reads, so lockout
        fields never go stale behind that endpoint's hour-long cache."""
        self.cache_manager.add(
            user_by_id_cache_key(str(user.id)),
            json.dumps(user.to_dict()),
            expiry=expiry,
        )

    def _ensure_timezone_aware(self, dt: datetime) -> datetime:
        """Ensure datetime is timezone-aware (assumes UTC if naive)"""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def _is_currently_locked(self, locked_until: Optional[datetime]) -> bool:
        if not locked_until:
            return False
        return self._ensure_timezone_aware(locked_until) >= datetime.now(timezone.utc)

    async def _clear_lockout(self, user: User) -> None:
        updated = await self.user_repository.find_one_and_update(
            {'id': user.id},
            refresh=True,
            failed_attempts=0,
            locked_until=None,
            last_failed_attempt=None,
        )
        if updated:
            self._cache_user(updated)

    async def check_account_lockout(
        self, user: User
    ) -> Tuple[bool, Optional[datetime]]:
        """
        Check if user account is locked.
        Returns (is_locked, locked_until_time)
        """
        if self._is_currently_locked(user.locked_until):
            logger.info(f'User {user.email} is locked until {user.locked_until}')
            return True, user.locked_until

        return False, None

    async def handle_failed_login(self, user: User) -> Tuple[bool, Optional[datetime]]:
        """
        Handle failed login attempt. Returns (is_now_locked, locked_until_time)
        """

        current_time = datetime.now(timezone.utc)

        failed_attempts = user.failed_attempts or 0
        locked_until = user.locked_until

        # An expired lock clears the slate. Without this the attempts counted
        # during the lockout would re-lock the account on the first mistake after
        # it runs out.
        lock_expired = locked_until is not None and not self._is_currently_locked(
            locked_until
        )

        # Reset attempts if enough time has passed or if this is the first failure
        if (
            lock_expired
            or user.last_failed_attempt is None
            or current_time - self._ensure_timezone_aware(user.last_failed_attempt)
            > timedelta(hours=self.lockout_duration_hours)
        ):
            failed_attempts = 0
            locked_until = None

        # Increment failed attempts
        failed_attempts += 1

        # Check if account should be locked
        if failed_attempts >= self.max_failed_attempts:
            locked_until = current_time + timedelta(hours=self.lockout_duration_hours)

        updated = await self.user_repository.find_one_and_update(
            {'id': user.id},
            refresh=True,
            failed_attempts=failed_attempts,
            locked_until=locked_until,
            last_failed_attempt=current_time,
        )
        if not updated:
            return False, None

        self._cache_user(
            updated,
            expiry=self.get_lockout_time_remaining(updated.locked_until)
            or USER_CACHE_TTL_SECONDS,
        )

        if updated.locked_until:
            logger.warning(
                f'User {user.email} account locked due to {failed_attempts} failed attempts'
            )
            return True, updated.locked_until

        logger.info(
            f'Failed login for {user.email}. Attempts: {failed_attempts}/{self.max_failed_attempts}'
        )
        return False, None

    async def record_locked_attempt(self, user: User) -> None:
        """Count a wrong password entered while the account is already locked.

        `locked_until` is deliberately left alone: extending it on every attempt
        would let anyone keep an account locked out indefinitely.
        """
        updated = await self.user_repository.find_one_and_update(
            {'id': user.id},
            refresh=True,
            failed_attempts=(user.failed_attempts or 0) + 1,
            last_failed_attempt=datetime.now(timezone.utc),
        )
        if not updated:
            return

        self._cache_user(
            updated,
            expiry=self.get_lockout_time_remaining(updated.locked_until)
            or USER_CACHE_TTL_SECONDS,
        )
        logger.info(
            f'Failed login for locked account {user.email}. '
            f'Attempts: {updated.failed_attempts}'
        )

    async def reset_failed_attempts(self, user: User) -> None:
        """Reset failed attempts on successful login"""

        if user.failed_attempts > 0 or user.locked_until or user.last_failed_attempt:
            await self._clear_lockout(user)
            logger.info(f'Reset failed attempts for user {user.email}')

    def get_lockout_time_remaining(self, locked_until: Optional[datetime]) -> int:
        """Get remaining lockout time in seconds"""
        if not locked_until:
            return 0

        current_time = datetime.now(timezone.utc)
        locked_until_aware = self._ensure_timezone_aware(locked_until)

        if locked_until_aware <= current_time:
            return 0

        return int((locked_until_aware - current_time).total_seconds())

    async def admin_unblock_user(self, user_id: str) -> bool:
        """Admin method to manually unblock a user account"""
        user = await self.user_repository.find_one(id=user_id)
        if not user:
            return False

        await self._clear_lockout(user)
        logger.info(f'Admin unblocked user account: {user_id}')
        return True
