"""Guardrail policy CRUD with caching."""

import json
from typing import Any, Dict, List

from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.guardrail_policy import GuardrailPolicy
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from guardrails_module.utils.cache_utils import get_guardrail_policy_cache_key


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

        cached = self.cache_manager.get_str(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                # A poisoned cache entry must not take the endpoint down.
                logger.warning(
                    f'Discarding unreadable guardrail policy cache for {namespace}'
                )
                self.cache_manager.remove(cache_key)

        policy = await self.guardrail_policy_repository.find_one(namespace=namespace)
        policy_dict = policy.to_dict() if policy else self.default_policy(namespace)

        self.cache_manager.add(
            cache_key, json.dumps(policy_dict), expiry=self.policy_cache_time
        )
        return policy_dict

    async def update_policy(
        self,
        namespace: str,
        is_enabled: bool,
        mode: str,
        adapters: List[Dict[str, Any]],
        stream: str = 'BUFFERED',
    ) -> Dict[str, Any]:
        """Create or replace a namespace's policy."""
        logger.info(
            f'Updating guardrail policy for namespace {namespace} - '
            f'enabled={is_enabled}, mode={mode}, adapters={len(adapters)}, '
            f'stream={stream}'
        )

        # policy_config is replaced wholesale, so every key it should carry
        # has to be written here. A caller that omits one silently reverts it.
        await self.guardrail_policy_repository.upsert(
            {'namespace': namespace},
            is_enabled=is_enabled,
            mode=mode,
            policy_config={'adapters': adapters, 'stream': stream},
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
            # Absent on every row written before the field existed, which is
            # the same answer those rows were enforcing anyway.
            'stream': config.get('stream', 'BUFFERED'),
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
    stream: Any = None,
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
    from flo_ai.guardrails.contracts import StreamCapability

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

    # Unlike a malformed adapter entry above, an unrecognised stream value is
    # logged and defaulted rather than raised on. The two failures are not
    # comparable: a bad adapter entry means a check the operator believes is
    # running is not, so the whole policy is refused; a bad stream value means
    # the response is delivered more slowly than asked for, which costs
    # latency and nothing else.
    resolved_stream = StreamCapability.BUFFERED
    if stream is not None:
        try:
            resolved_stream = StreamCapability(stream)
        except ValueError:
            logger.warning(
                f'Unknown guardrail stream mode {stream!r} in {describe}; '
                f'buffering the response instead'
            )

    return ResolvedPolicy(
        is_enabled=True,
        mode=EnforcementMode(mode),
        adapters=tuple(specs),
        version=version,
        stream=resolved_stream,
    )


class DatabasePolicyResolver:
    """Adapts GuardrailsService to flo_ai's PolicyResolver port.

    Keeps the SDK storage-agnostic: flo_ai depends on a protocol with a single
    ``resolve`` method and never learns about Postgres or Redis.
    """

    def __init__(self, guardrails_service: GuardrailsService):
        self.guardrails_service = guardrails_service

    async def resolve(self, principal: Any):
        from flo_ai.guardrails.contracts import DISABLED_POLICY

        namespace = getattr(principal, 'namespace', None)
        if not namespace:
            # No namespace means nothing to look up. Enforcing a guessed
            # policy would be worse than not enforcing one.
            return DISABLED_POLICY

        policy = await self.guardrails_service.get_policy(namespace)
        if not policy.get('is_enabled'):
            return DISABLED_POLICY

        config = policy.get('policy_config') or {}
        return build_resolved_policy(
            mode=policy.get('mode', 'MONITOR'),
            adapter_entries=config.get('adapters', []),
            version=policy.get('updated_at'),
            describe=f'namespace {namespace}',
            stream=config.get('stream'),
        )
