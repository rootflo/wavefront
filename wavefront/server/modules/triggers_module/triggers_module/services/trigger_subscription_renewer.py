from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from common_module.common_cache import CommonCache
from common_module.log.logger import logger
from db_repo_module.models.agentic_trigger import AgenticTrigger
from db_repo_module.models.agentic_trigger_credential import AgenticTriggerCredential
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository

from triggers_module.providers.base import TriggerProvider
from triggers_module.providers.registry import TriggerProviderRegistry
from triggers_module.utils.token_crypto import TokenCrypto


class TriggerSubscriptionRenewer:
    """Periodically renews provider subscriptions/watches that are about to
    expire. Designed to be called from the floware APScheduler poller."""

    def __init__(
        self,
        trigger_repository: SQLAlchemyRepository[AgenticTrigger],
        credential_repository: SQLAlchemyRepository[AgenticTriggerCredential],
        provider_registry: TriggerProviderRegistry,
        token_crypto: TokenCrypto,
        cache_manager: CommonCache,
        renew_window_hours: int = 24,
    ):
        self._triggers = trigger_repository
        self._credentials = credential_repository
        self._registry = provider_registry
        self._crypto = token_crypto
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
        if not trigger.credential_id or not trigger.provider_config:
            return
        provider = self._registry.get(trigger.provider)
        access_token, external_account_id = await self._fresh_access_token(
            trigger.credential_id, provider
        )
        updated_config = await provider.renew_subscription(
            provider_config=trigger.provider_config,
            access_token=access_token,
            external_account_id=external_account_id,
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

    async def _fresh_access_token(
        self, credential_id: UUID, provider: TriggerProvider
    ) -> tuple[str, str]:
        credential = await self._credentials.find_one(id=credential_id)
        if not credential:
            raise RuntimeError(f'Credential {credential_id} not found')

        now = datetime.now(timezone.utc)
        if (
            credential.encrypted_access_token
            and credential.token_expires_at
            and credential.token_expires_at > now
        ):
            return (
                self._crypto.decrypt(credential.encrypted_access_token) or '',
                credential.external_account_id,
            )

        refresh_token = self._crypto.decrypt(credential.encrypted_refresh_token)
        bundle = await provider.refresh_access_token(refresh_token or '')
        await self._credentials.find_one_and_update(
            {'id': credential_id},
            encrypted_access_token=self._crypto.encrypt(bundle.access_token),
            token_expires_at=bundle.expires_at,
        )
        return bundle.access_token or '', credential.external_account_id
