"""Guardrail policy CRUD with caching."""

import asyncio
import json
import time
from typing import Any, Dict, List

from sqlalchemy import func
from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.guardrail_policy import GuardrailPolicy
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from concurrent.futures import ThreadPoolExecutor
from guardrails_module.utils.cache_utils import get_guardrail_policy_cache_key

_CACHE_EXECUTOR = ThreadPoolExecutor(
    max_workers=32, thread_name_prefix='guardrails-cache'
)


class GuardrailsService:
    """Reads and writes per-namespace guardrail policy.

    A policy is read on every guarded LLM call, so reads are cached; without
    that, enabling guardrails would add a Postgres round trip to each one.
    """

    def __init__(
        self,
        guardrail_policy_repository: SQLAlchemyRepository[GuardrailPolicy],
        cache_manager: CacheManager,
    ):
        self.guardrail_policy_repository = guardrail_policy_repository
        self.cache_manager = cache_manager
        self.policy_cache_time = 300

    @staticmethod
    def default_policy(namespace: str) -> Dict[str, Any]:
        """What a namespace with no policy row gets.

        Disabled and in monitor mode: a namespace that has never been
        configured must not have traffic blocked, and absence of a row is not
        consent to enforce.
        """
        return {
            'namespace': namespace,
            'is_enabled': False,
            'mode': 'MONITOR',
            'policy_config': {'adapters': []},
            'created_at': None,
            'updated_at': None,
        }

    async def get_policy(self, namespace: str) -> Dict[str, Any]:
        """Return the effective policy, falling back to a disabled default."""
        cache_key = get_guardrail_policy_cache_key(namespace)

        loop = asyncio.get_running_loop()
        try:
            cached = await asyncio.wait_for(
                loop.run_in_executor(
                    _CACHE_EXECUTOR, self.cache_manager.get_str, cache_key
                ),
                0.25,
            )
        except (TimeoutError, asyncio.TimeoutError):
            logger.warning(f'Guardrails: Redis timeout fetching policy for {namespace}')
            cached = None
        except Exception as e:
            logger.warning(
                f'Guardrails: Redis error fetching policy for {namespace}: {e}'
            )
            cached = None

        if cached:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                # A poisoned cache entry must not take the endpoint down.
                logger.warning(
                    f'Discarding unreadable guardrail policy cache for {namespace}'
                )
                try:
                    await asyncio.wait_for(
                        loop.run_in_executor(
                            _CACHE_EXECUTOR, self.cache_manager.remove, cache_key
                        ),
                        0.25,
                    )
                except Exception:
                    pass

        policy = await self.guardrail_policy_repository.find_one(namespace=namespace)
        policy_dict = policy.to_dict() if policy else self.default_policy(namespace)

        try:
            # functools.partial is needed because run_in_executor doesn't take **kwargs directly
            import functools

            await asyncio.wait_for(
                loop.run_in_executor(
                    _CACHE_EXECUTOR,
                    functools.partial(
                        self.cache_manager.add,
                        cache_key,
                        json.dumps(policy_dict),
                        expiry=self.policy_cache_time,
                    ),
                ),
                0.25,
            )
        except Exception:
            pass
        return policy_dict

    async def update_policy(
        self,
        namespace: str,
        is_enabled: bool,
        mode: str,
        adapters: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Create or replace a namespace's policy."""
        logger.info(
            f'Updating guardrail policy for namespace {namespace} - '
            f'enabled={is_enabled}, mode={mode}, adapters={len(adapters)}'
        )

        await self.guardrail_policy_repository.upsert(
            {'namespace': namespace},
            is_enabled=is_enabled,
            mode=mode,
            policy_config={'adapters': adapters},
            updated_at=func.now(),
        )

        # Invalidate before re-reading so a concurrent reader cannot repopulate
        # the cache from the pre-update row.
        self.cache_manager.remove(get_guardrail_policy_cache_key(namespace))

        policy = await self.guardrail_policy_repository.find_one(namespace=namespace)
        return policy.to_dict() if policy else self.default_policy(namespace)

    async def list_policies(self) -> List[Dict[str, Any]]:
        """Every configured policy. Not cached; an admin-console read."""
        policies = await self.guardrail_policy_repository.find()
        return [policy.to_dict() for policy in policies]

    @staticmethod
    def to_response(policy: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten the stored shape into the API shape."""
        config = policy.get('policy_config') or {}
        return {
            'namespace': policy['namespace'],
            'is_enabled': policy['is_enabled'],
            'mode': policy['mode'],
            'adapters': config.get('adapters', []),
            'created_at': policy.get('created_at'),
            'updated_at': policy.get('updated_at'),
        }

    async def get_policy_response(self, namespace: str) -> Dict[str, Any]:
        return self.to_response(await self.get_policy(namespace))

    async def delete_policy(self, namespace: str) -> bool:
        """Remove a policy, reverting the namespace to the disabled default."""
        deleted = await self.guardrail_policy_repository.delete_all(namespace=namespace)
        self.cache_manager.remove(get_guardrail_policy_cache_key(namespace))
        return deleted


def build_resolved_policy(
    mode: str,
    adapter_entries: Any,
    version: Any = None,
    describe: str = 'policy',
):
    """Turn stored (or draft) adapter config into flo_ai's ResolvedPolicy.

    Shared by the resolver that feeds enforcement and by the preview endpoint,
    so a previewed policy is built by exactly the same code as the enforced
    one. Two conversions would eventually disagree, and the preview would then
    reassure an operator about behaviour that never happens.
    """
    from flo_ai.guardrails import (
        AdapterSpec,
        EnforcementMode,
        FailureMode,
        ResolvedPolicy,
        WorkflowStage,
    )

    specs = []
    for entry in adapter_entries or []:
        try:
            specs.append(
                AdapterSpec(
                    name=entry['name'],
                    stages=tuple(
                        WorkflowStage(stage) for stage in entry.get('stages', [])
                    ),
                    on_error=FailureMode(entry.get('on_error', 'FAIL_OPEN')),
                    timeout_seconds=float(entry.get('timeout_seconds', 5.0)),
                    options=entry.get('options') or {},
                )
            )
        except (KeyError, ValueError) as exc:
            # Skipping a malformed entry would quietly drop a check the
            # operator believes is running, so refuse the whole policy and
            # let the engine's misconfiguration path fail closed.
            logger.error(
                f'Malformed guardrail adapter config in {describe}: '
                f'{entry!r} ({exc})'
            )
            raise

    return ResolvedPolicy(
        is_enabled=True,
        mode=EnforcementMode(mode),
        adapters=tuple(specs),
        version=version,
    )


class DatabasePolicyResolver:
    """Adapts GuardrailsService to flo_ai's PolicyResolver port.

    Keeps the SDK storage-agnostic: flo_ai depends on a protocol with a single
    ``resolve`` method and never learns about Postgres or Redis.
    """

    def __init__(self, guardrails_service: GuardrailsService):
        self.guardrails_service = guardrails_service
        # Seconds a resolved policy is reused in-process. Bounds how long an
        # edit takes to reach other workers, and removes Redis from the
        # per-call path.
        self._ttl = 5.0
        self._memo: dict = {}

    async def resolve(self, principal: Any):
        from flo_ai.guardrails.contracts import DISABLED_POLICY

        namespace = getattr(principal, 'namespace', None)
        if not namespace:
            # No namespace means nothing to look up. Enforcing a guessed
            # policy would be worse than not enforcing one.
            return DISABLED_POLICY

        hit = self._memo.get(namespace)
        if hit and hit[0] > time.monotonic():
            policy = hit[1]
        else:
            policy = await self.guardrails_service.get_policy(namespace)
            self._memo[namespace] = (time.monotonic() + self._ttl, policy)
        if not policy.get('is_enabled'):
            return DISABLED_POLICY

        return build_resolved_policy(
            mode=policy.get('mode', 'MONITOR'),
            adapter_entries=(policy.get('policy_config') or {}).get('adapters', []),
            version=policy.get('updated_at'),
            describe=f'namespace {namespace}',
        )
