from datetime import datetime, timedelta, timezone
from typing import Optional

from common_module.common_cache import CommonCache
from common_module.log.logger import logger
from db_repo_module.models.agentic_trigger import AgenticTrigger
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from mailer import EmailCapability
from plugins_module.services.email_connection_service import EmailConnectionService


class TriggerSubscriptionRenewer:
    """Periodically renews provider subscriptions/watches that are about to
    expire. Designed to be called from the floware APScheduler poller."""

    def __init__(
        self,
        trigger_repository: SQLAlchemyRepository[AgenticTrigger],
        email_connection_service: EmailConnectionService,
        cache_manager: CommonCache,
        renew_window_hours: int = 24,
    ):
        self._triggers = trigger_repository
        self._connections = email_connection_service
        self._cache = cache_manager
        self._renew_window = timedelta(hours=renew_window_hours)

    async def run_once(self) -> int:
        lock_key = 'lock:trigger_subscription_renewer'
        # Try to acquire lock with a 30-minute expiry (1800 seconds)
        # using the atomic Set-if-Not-Exists (nx=True) flag
        acquired = self._cache.add(lock_key, 'locked', expiry=1800, nx=True)
        if not acquired:
            logger.info(
                'TriggerSubscriptionRenewer: lock already held in Redis. Skipping run.'
            )
            return 0

        # Note: we intentionally do NOT release the lock on completion.
        # Letting the TTL expire avoids a compare-and-delete race where a pod
        # whose work outran the TTL would otherwise delete another pod's
        # freshly-acquired lock. The next cron fire is 6h away, well past the
        # 30-min TTL.
        logger.info(
            'TriggerSubscriptionRenewer: successfully acquired Redis lock. Starting watches renewal.'
        )
        renewed = 0
        active = await self._triggers.find(status='active', limit=1000)
        cutoff = datetime.now(timezone.utc) + self._renew_window

        for trigger in active:
            try:
                expiration = self._extract_expiration(trigger.provider_config)
                if expiration is None or expiration > cutoff:
                    continue
                await self._renew_one(trigger)
                renewed += 1
            except Exception as exc:
                logger.warning(
                    f'Failed to renew subscription for trigger {trigger.id}: {exc}'
                )
                await self._triggers.find_one_and_update(
                    {'id': trigger.id},
                    last_error=f'renew failed: {exc}',
                )
        return renewed

    async def _renew_one(self, trigger: AgenticTrigger) -> None:
        if not trigger.provider_config:
            return

        connection = await self._connections.require_active(trigger.connection_id)
        access_token, mailbox = await self._connections.get_access_token(
            trigger.connection_id, capabilities=[EmailCapability.READ]
        )
        provider = await self._connections.get_provider(connection)

        updated_config = await provider.renew_watch(
            access_token=access_token,
            mailbox=mailbox,
            provider_config=trigger.provider_config,
        )
        await self._triggers.find_one_and_update(
            {'id': trigger.id},
            provider_config=updated_config,
            last_error=None,
        )

    @staticmethod
    def _extract_expiration(provider_config: Optional[dict]) -> Optional[datetime]:
        if not provider_config:
            return None
        raw = provider_config.get('watch_expiration')
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw)
        except Exception:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
