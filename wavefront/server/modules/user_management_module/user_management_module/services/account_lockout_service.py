from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.user import User
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository


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

    def _get_cache_key(self, user_email: str) -> str:
        return f'locked:{user_email}'

    def _ensure_timezone_aware(self, dt: datetime) -> datetime:
        """Ensure datetime is timezone-aware (assumes UTC if naive)"""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def _parse_cached_datetime(self, iso_string: str) -> Optional[datetime]:
        """Parse cached ISO datetime string safely"""
        try:
            return datetime.fromisoformat(iso_string)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse cached datetime '{iso_string}': {e}")
            return None

    async def check_account_lockout(
        self, user_email: str
    ) -> Tuple[bool, Optional[datetime]]:
        """
        Check if user account is locked.
        Returns (is_locked, locked_until_time)
        """
        # First check cache for performance
        cache_key = self._get_cache_key(user_email)
        cached_lockout = self.cache_manager.get_str(cache_key)

        if cached_lockout:
            # Parse cached locked_until datetime
            cached_locked_until = self._parse_cached_datetime(cached_lockout)
            if cached_locked_until:
                logger.info(
                    f'User {user_email} is locked until {cached_locked_until} (from cache)'
                )
                return True, cached_locked_until
            # If parsing failed, fall through to database check

        # Check database as fallback
        user = await self.user_repository.find_one(email=user_email)
        if not user:
            return False, None

        current_time = datetime.now(timezone.utc)

        if (
            user.locked_until
            and self._ensure_timezone_aware(user.locked_until) >= current_time
        ):
            # User is locked, update cache with remaining time
            locked_until_aware = self._ensure_timezone_aware(user.locked_until)
            remaining_seconds = int((locked_until_aware - current_time).total_seconds())
            self.cache_manager.add(
                cache_key, locked_until_aware.isoformat(), expiry=remaining_seconds
            )
            logger.info(f'User {user_email} is locked until {user.locked_until}')
            return True, user.locked_until

        return False, None

    async def handle_failed_login(self, user: User) -> Tuple[bool, Optional[datetime]]:
        """
        Handle failed login attempt. Returns (is_now_locked, locked_until_time)
        """

        current_time = datetime.now(timezone.utc)

        # Reset attempts if enough time has passed or if this is the first failure
        if (
            user.last_failed_attempt is None
            or current_time - self._ensure_timezone_aware(user.last_failed_attempt)
            > timedelta(hours=self.lockout_duration_hours)
        ):
            user.failed_attempts = 0
            user.locked_until = None

        # Increment failed attempts
        user.failed_attempts += 1
        user.last_failed_attempt = current_time

        # Check if account should be locked
        if user.failed_attempts >= self.max_failed_attempts:
            user.locked_until = current_time + timedelta(
                hours=self.lockout_duration_hours
            )

            # Set cache with lockout
            cache_key = self._get_cache_key(user.email)
            cache_expiry_seconds = self.lockout_duration_hours * 60 * 60
            self.cache_manager.add(
                cache_key, user.locked_until.isoformat(), expiry=cache_expiry_seconds
            )

            await self.user_repository.find_one_and_update(
                {'id': user.id},
                failed_attempts=user.failed_attempts,
                locked_until=user.locked_until,
                last_failed_attempt=user.last_failed_attempt,
            )

            logger.warning(
                f'User {user.email} account locked due to {user.failed_attempts} failed attempts'
            )
            return True, user.locked_until

        # Update user with new failed attempt count
        await self.user_repository.find_one_and_update(
            {'id': user.id},
            failed_attempts=user.failed_attempts,
            locked_until=user.locked_until,
            last_failed_attempt=user.last_failed_attempt,
        )

        logger.info(
            f'Failed login for {user.email}. Attempts: {user.failed_attempts}/{self.max_failed_attempts}'
        )
        return False, None

    async def reset_failed_attempts(self, user: User) -> None:
        """Reset failed attempts on successful login"""

        if user.failed_attempts > 0 or user.locked_until or user.last_failed_attempt:
            user.failed_attempts = 0
            user.locked_until = None
            user.last_failed_attempt = None
            await self.user_repository.find_one_and_update(
                {'id': user.id},
                failed_attempts=user.failed_attempts,
                locked_until=user.locked_until,
                last_failed_attempt=user.last_failed_attempt,
            )

            # Clear cache
            cache_key = self._get_cache_key(user.email)
            self.cache_manager.remove(cache_key)

            logger.info(f'Reset failed attempts for user {user.email}')

    async def _reset_lockout(self, user: User) -> None:
        """Internal method to reset lockout status"""
        user.failed_attempts = 0
        user.locked_until = None
        user.last_failed_attempt = None
        await self.user_repository.find_one_and_update(
            {'id': user.id},
            failed_attempts=user.failed_attempts,
            locked_until=user.locked_until,
            last_failed_attempt=user.last_failed_attempt,
        )

        # Clear cache
        cache_key = self._get_cache_key(user.email)
        self.cache_manager.remove(cache_key)

    def get_lockout_time_remaining(self, locked_until: datetime) -> int:
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

        # Reset lockout status
        await self._reset_lockout(user)
        logger.info(f'Admin unblocked user account: {user_id}')
        return True
