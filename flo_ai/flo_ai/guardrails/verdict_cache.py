"""Records of verdicts the engine already derived, and what may leave the process.

The cache exists because one message is evaluated many times: a conversation
re-sends its history every turn, a tool-calling loop re-sends the turn on every
iteration, and a workflow runs many nodes over one namespace's policy. A safety
provider bills per call and answers the same thing each time.

Two backends, because the two have different rules about content. An
in-process cache may hold anything the engine produced, since nothing leaves
the process that did not already have it. A *shared* cache — Redis, typically —
is a separate security domain: operators can read it, it is snapshotted to
disk, and its credentials are spread across every service that talks to it. So
``encode_decision`` refuses to serialise any decision carrying a message body,
and that refusal is the one place the guarantee lives.

What survives the refusal is the part that was already content-free by
contract: the action, the finding codes, entity *types* and counts, severity,
the policy version. Exactly what ``CheckResult.provider_metadata`` is
documented to hold, and what the audit trail already persists.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any, List, Optional, Protocol, Tuple

from flo_ai.utils.logger import logger

from .contracts import (
    AssessmentStatus,
    CheckResult,
    FailureClass,
    PolicyAction,
    PolicyDecision,
)

#: Ceiling on the text one in-process cache keeps, in characters.
#:
#: Bounded by size rather than entry count because the values may hold redacted
#: message bodies. Charged per entry as well, so a cache of many tiny clean
#: verdicts is bounded too.
VERDICT_CACHE_CHAR_BUDGET = 1_000_000

_ENTRY_OVERHEAD_CHARS = 256

#: Bumped whenever the serialised shape changes. A reader that does not
#: recognise the version treats the entry as a miss rather than guessing, so a
#: rolling deploy where both versions are live cannot mis-decode the other's
#: entries into a wrong verdict.
SCHEMA_VERSION = 1


class VerdictCache(Protocol):
    """Port for remembering a decision under a key the engine derived.

    Async because a shared backend is a network call. The in-process
    implementation satisfies it without ever suspending.

    Implementations must not raise. A cache is an optimisation, and one that
    can fail a request it was only meant to speed up is worse than no cache:
    every failure mode here has ``return None`` as its correct answer.
    """

    async def get(self, key: str) -> Optional[PolicyDecision]: ...

    async def store(self, key: str, decision: PolicyDecision) -> None: ...


def carries_content(decision: PolicyDecision) -> bool:
    """Whether ``decision`` holds any part of the payload it judged.

    Only transforms do. A TRANSFORM carries the rewritten text so the caller
    can send it on, and that text is the evaluated message minus whatever the
    adapter detected — which is not the same as a message with no PII in it.
    Presidio removes the entity types the policy selected, above the configured
    score threshold. Anything unselected, sub-threshold or unrecognised is
    still there, verbatim.
    """
    if decision.transformed_content is not None:
        return True
    return any(result.transformed_content is not None for result in decision.results)


def encode_decision(decision: PolicyDecision) -> Optional[str]:
    """Serialise ``decision`` for a shared cache, or ``None`` if it may not go.

    The single gate on what reaches Redis. Returning ``None`` is a refusal to
    store, never an error: the caller treats it as "this one is not shareable"
    and the verdict is simply re-derived elsewhere.
    """
    if carries_content(decision):
        return None

    payload = {
        'v': SCHEMA_VERSION,
        'action': decision.action.value,
        'observed': decision.observed_action.value,
        'enforced': decision.enforced,
        'policy_version': decision.policy_version,
        'results': [
            {
                'status': result.status.value,
                'action': result.action.value,
                'adapter': result.adapter,
                'finding_code': result.finding_code,
                'message': result.message,
                'failure_class': result.failure_class.value,
                'severity': result.severity,
                'metadata': result.provider_metadata,
            }
            for result in decision.results
        ],
    }

    try:
        return json.dumps(payload, separators=(',', ':'))
    except (TypeError, ValueError) as exc:
        # An adapter put something unserialisable in provider_metadata. Not
        # worth failing the request over, but worth saying out loud: it means
        # this adapter's verdicts silently stop being shared.
        logger.warning(f'Guardrail verdict could not be serialised for cache: {exc}')
        return None


def decode_decision(raw: str) -> Optional[PolicyDecision]:
    """Rebuild a decision from ``encode_decision`` output, or ``None``.

    Anything unrecognised — a future schema, a truncated value, an enum member
    this version does not have — is a miss. The cost of a miss is one
    re-evaluation; the cost of guessing is enforcing a verdict nobody reached.
    """
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None

    if not isinstance(payload, dict) or payload.get('v') != SCHEMA_VERSION:
        return None

    try:
        results: List[CheckResult] = [
            CheckResult(
                status=AssessmentStatus(item['status']),
                action=PolicyAction(item['action']),
                adapter=item.get('adapter'),
                finding_code=item.get('finding_code'),
                message=item.get('message'),
                failure_class=FailureClass(item.get('failure_class', 'NONE')),
                severity=item.get('severity'),
                provider_metadata=item.get('metadata') or {},
            )
            for item in payload.get('results', [])
        ]
        return PolicyDecision(
            action=PolicyAction(payload['action']),
            results=results,
            transformed_content=None,
            enforced=bool(payload.get('enforced', True)),
            observed_action=PolicyAction(payload['observed']),
            policy_version=payload.get('policy_version'),
        )
    except (KeyError, TypeError, ValueError):
        return None


class LocalVerdictCache:
    """Bounded, in-process record of decisions this engine already derived.

    Keyed by content *and* by the policy that judged it, so an edited policy
    cannot replay verdicts from the previous one. A miss re-derives, which
    makes eviction a question of cost and never of what reaches a provider.

    Holds transforms, unlike a shared cache: the redacted body is already in
    this process, sitting next to the original that produced it, so keeping it
    here spreads nothing that was not already here.

    Decisions are handed out by reference, on the same read-only footing as the
    ones ``evaluate`` returns fresh. Two callers evaluating identical content at
    the same instant can both miss and both derive it, which costs a duplicate
    call and nothing else; only a fan-out over identical payloads would notice.
    """

    def __init__(self, char_budget: int = VERDICT_CACHE_CHAR_BUDGET) -> None:
        self._budget = char_budget
        self._entries: 'OrderedDict[str, Tuple[PolicyDecision, int]]' = OrderedDict()
        self._chars = 0

    async def get(self, key: str) -> Optional[PolicyDecision]:
        entry = self._entries.get(key)
        if entry is None:
            return None
        self._entries.move_to_end(key)
        return entry[0]

    async def store(self, key: str, decision: PolicyDecision) -> None:
        if self._budget <= 0:
            return

        cost = _ENTRY_OVERHEAD_CHARS + (
            len(decision.transformed_content)
            if isinstance(decision.transformed_content, str)
            else 0
        )
        previous = self._entries.pop(key, None)
        if previous is not None:
            self._chars -= previous[1]
        self._entries[key] = (decision, cost)
        self._chars += cost

        # Oldest first, so what survives is what traffic is still touching.
        while self._entries and self._chars > self._budget:
            _, (_, evicted_cost) = self._entries.popitem(last=False)
            self._chars -= evicted_cost


class TieredVerdictCache:
    """An in-process cache in front of a shared one.

    The two tiers are not redundant, because they hold different things. The
    shared tier refuses transforms, so for a redaction policy the local tier is
    not an optimisation over it — it is the only place a redaction is
    remembered at all. The shared tier, in turn, is the only thing that helps a
    process that has just started, which is the common case: workers restart,
    scale out, and run one conversation's turns on different processes.

    A shared hit is promoted into the local tier, so a message being re-sent
    round a tool-calling loop costs one round trip rather than one per
    iteration.
    """

    def __init__(self, local: VerdictCache, shared: VerdictCache) -> None:
        self._local = local
        self._shared = shared

    async def get(self, key: str) -> Optional[PolicyDecision]:
        decision = await self._local.get(key)
        if decision is not None:
            return decision

        decision = await self._shared_call(self._shared.get(key))
        if decision is not None:
            await self._local.store(key, decision)
        return decision

    async def store(self, key: str, decision: PolicyDecision) -> None:
        await self._local.store(key, decision)
        # Silently keeps only what is shareable; see encode_decision.
        await self._shared_call(self._shared.store(key, decision))

    @staticmethod
    async def _shared_call(awaitable: Any) -> Any:
        """Run a shared-tier call, swallowing anything it throws.

        The port asks implementations not to raise, and the Redis one holds to
        it. This is here anyway because the failure it prevents is the worst
        one available: a cache that exists to save a provider call would
        instead be failing the inference request that the provider call was
        for. The local tier is unaffected, so an outage degrades to
        per-process caching rather than to no caching.
        """
        try:
            return await awaitable
        except Exception as exc:
            logger.debug(f'Guardrail shared verdict cache unavailable: {exc}')
            return None


class NullVerdictCache:
    """Remembers nothing. For turning caching off without branching on it."""

    async def get(self, key: str) -> Optional[PolicyDecision]:
        return None

    async def store(self, key: str, decision: PolicyDecision) -> None:
        return None


def build_local_cache(char_budget: int) -> VerdictCache:
    """A local cache, or a null one when the budget is zero or negative."""
    if char_budget <= 0:
        return NullVerdictCache()
    return LocalVerdictCache(char_budget)


__all__ = [
    'SCHEMA_VERSION',
    'VERDICT_CACHE_CHAR_BUDGET',
    'LocalVerdictCache',
    'NullVerdictCache',
    'TieredVerdictCache',
    'VerdictCache',
    'build_local_cache',
    'carries_content',
    'decode_decision',
    'encode_decision',
]
