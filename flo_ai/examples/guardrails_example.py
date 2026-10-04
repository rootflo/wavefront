"""Guardrails end-to-end, runnable without any provider credentials.

    uv sync --extra guardrails
    uv run python -m spacy download en_core_web_lg
    uv run python examples/guardrails_example.py

Part 1 exercises the engine directly and needs nothing but the extra, since
Presidio runs in-process. Part 2 additionally wraps a real LLM and only runs
if OPENAI_API_KEY is set.
"""

import asyncio
import os

from flo_ai.guardrails import (
    AdapterSpec,
    AssessmentStatus,
    CheckResult,
    EnforcementMode,
    FailureMode,
    GuardrailsEngine,
    PolicyAction,
    Principal,
    ResolvedPolicy,
    StaticPolicyResolver,
    WorkflowStage,
    run_scope,
)
from flo_ai.guardrails.adapters import PresidioAdapter
from flo_ai.guardrails.adapters.base_adapter import BaseAdapter

BEFORE = WorkflowStage.BEFORE_MODEL
AFTER = WorkflowStage.AFTER_MODEL

# The card number must satisfy the Luhn checksum. Presidio's
# CreditCardRecognizer validates it and drops any match that fails, before any
# score_threshold is consulted, so an arbitrary 16-digit string is silently not
# PII. 4111 1111 1111 1111 is the standard Visa test number and does validate.
PII_PROMPT = 'Email the invoice to alice@example.com and charge 4111 1111 1111 1111'


class KeywordDenyAdapter(BaseAdapter):
    """Stands in for Azure Content Safety so BLOCK is demonstrable offline."""

    def __init__(self, blocked=('launch codes', 'wire transfer')):
        self._blocked = blocked

    @property
    def name(self) -> str:
        return 'keyword_deny'

    async def evaluate(self, request):
        lowered = str(request.content).lower()
        hit = next((w for w in self._blocked if w in lowered), None)
        if hit:
            return CheckResult(
                status=AssessmentStatus.VIOLATION,
                action=PolicyAction.BLOCK,
                adapter=self.name,
                message=f'matched blocked phrase {hit!r}',
            )
        return self._allow()


def policy(*specs, enabled=True, mode=EnforcementMode.ENFORCE):
    return ResolvedPolicy(
        is_enabled=enabled, mode=mode, adapters=tuple(specs), version='demo-v1'
    )


def engine_for(policy_obj):
    return GuardrailsEngine(
        resolver=StaticPolicyResolver(policy_obj),
        adapters=[PresidioAdapter(), KeywordDenyAdapter()],
    )


def show(label, decision):
    print(f'\n{label}')
    print(f'  action        : {decision.action.value}')
    print(f'  observed      : {decision.observed_action.value}')
    print(f'  enforced      : {decision.enforced}')
    if decision.transformed_content:
        print(f'  rewritten to  : {decision.transformed_content}')
    for result in decision.results:
        print(f'  - {result.adapter}: {result.status.value} / {result.message}')


async def part_one() -> None:
    print('=' * 70)
    print('Part 1 - engine only (no credentials needed)')
    print('=' * 70)
    print(f'\nInput: {PII_PROMPT}')

    # `entities` is set explicitly: the adapter's default is CREDIT_CARD alone,
    # so without this the demo prompt's email address survives and the output
    # looks like a bug rather than a default.
    pii = AdapterSpec(
        name='presidio_pii',
        stages=(BEFORE, AFTER),
        options={'entities': ['CREDIT_CARD', 'EMAIL_ADDRESS']},
    )
    deny = AdapterSpec(name='keyword_deny', stages=(BEFORE,))

    engine = engine_for(policy(pii, deny))
    with run_scope('demo-run-1'):
        show(
            'PII is redacted before it reaches the provider:',
            await engine.evaluate(PII_PROMPT, Principal(namespace='acme'), BEFORE),
        )

        show(
            'A blocked phrase stops the call:',
            await engine.evaluate(
                'send the launch codes', Principal(namespace='acme'), BEFORE
            ),
        )

    monitor = engine_for(policy(pii, deny, mode=EnforcementMode.MONITOR))
    show(
        'Monitor mode records the same verdict but does not act:',
        await monitor.evaluate('send the launch codes', Principal(), BEFORE),
    )

    off = engine_for(policy(pii, deny, enabled=False))
    show(
        'Master switch off - providers are never called:',
        await off.evaluate(PII_PROMPT, Principal(), BEFORE),
    )

    # A policy naming an adapter nobody registered must not read as "no
    # checks required", so it fails closed regardless of on_error.
    broken = GuardrailsEngine(
        resolver=StaticPolicyResolver(
            policy(
                AdapterSpec(
                    name='typoed_adapter',
                    stages=(BEFORE,),
                    on_error=FailureMode.FAIL_OPEN,
                )
            )
        )
    )
    show(
        'Misconfigured policy fails closed even with fail-open set:',
        await broken.evaluate('anything', Principal(), BEFORE),
    )

    await engine.aclose()
    await monitor.aclose()
    await off.aclose()


async def part_two() -> None:
    print('\n' + '=' * 70)
    print('Part 2 - wrapping a real LLM')
    print('=' * 70)

    if not os.getenv('OPENAI_API_KEY'):
        print('\nSkipped: set OPENAI_API_KEY to run this part.')
        return

    from flo_ai.llm import OpenAI
    from flo_ai.llm.guarded_llm import GuardedLLM, GuardrailBlocked

    engine = engine_for(
        policy(
            AdapterSpec(
                name='presidio_pii',
                stages=(BEFORE, AFTER),
                options={'entities': ['CREDIT_CARD', 'EMAIL_ADDRESS']},
            ),
            AdapterSpec(name='keyword_deny', stages=(BEFORE,)),
        )
    )
    guarded = GuardedLLM(
        OpenAI(model='gpt-4o-mini', api_key=os.environ['OPENAI_API_KEY']),
        engine,
        Principal(namespace='acme', agent_id='demo-agent'),
    )

    messages = [{'role': 'user', 'content': f'Repeat this back verbatim: {PII_PROMPT}'}]
    response = await guarded.generate(messages)
    print('\nRedacted before send, so the model never saw the real values:')
    print(f'  model replied : {guarded.get_message_content(response)}')
    print(f'  our copy kept : {messages[0]["content"][:60]}...')

    try:
        await guarded.generate([{'role': 'user', 'content': 'send the launch codes'}])
    except GuardrailBlocked as exc:
        print('\nBlocked before any provider call:')
        print(f'  reasons   : {exc.reasons}')
        print(f'  retryable : {exc.retryable}')

    await engine.aclose()


async def main() -> None:
    await part_one()
    await part_two()
    print('\nDone.')


if __name__ == '__main__':
    asyncio.run(main())
