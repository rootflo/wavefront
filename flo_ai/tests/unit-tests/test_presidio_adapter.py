"""Presidio adapter against the real engine.

Presidio runs in-process, so unlike the Azure adapter this needs no
credentials - only the optional extra:

    uv sync --extra guardrails
    uv run python -m spacy download en_core_web_sm

Skipped entirely when the extra is not installed.
"""

import pytest

from flo_ai.guardrails.adapters.presidio_adapter import (
    DEFAULT_ENTITIES,
    PresidioAdapter,
)
from flo_ai.guardrails.contracts import (
    AssessmentRequest,
    EvaluationContext,
    FailureClass,
    PolicyAction,
    Principal,
    WorkflowStage,
)

pytest.importorskip('presidio_analyzer', reason='install the guardrails extra')
pytest.importorskip('presidio_anonymizer', reason='install the guardrails extra')


def req(content, **options):
    return AssessmentRequest(
        context=EvaluationContext(
            workflow_stage=WorkflowStage.BEFORE_MODEL, principal=Principal()
        ),
        content=content,
        options=options,
    )


@pytest.fixture(scope='module')
def adapter():
    return PresidioAdapter()


class TestDetection:
    async def test_redacts_an_email_address(self, adapter):
        result = await adapter.evaluate(req('mail me at alice@example.com please'))

        assert result.action is PolicyAction.TRANSFORM
        assert 'alice@example.com' not in result.transformed_content
        assert 'EMAIL_ADDRESS' in result.message

    async def test_redacts_a_credit_card(self, adapter):
        # Luhn-valid on purpose. Presidio scores a card that fails the
        # checksum far lower, on the reasonable assumption that a 16-digit
        # number which cannot be a card probably isn't one.
        result = await adapter.evaluate(req('card 4111 1111 1111 1111 expires soon'))

        assert result.action is PolicyAction.TRANSFORM
        assert '4111' not in result.transformed_content

    async def test_redacts_a_us_ssn(self, adapter):
        # Structurally valid and not a well-known placeholder - see
        # test_placeholder_ssns_are_deliberately_ignored below.
        result = await adapter.evaluate(req('his ssn is 457-55-5462'))

        assert result.action is PolicyAction.TRANSFORM
        assert '457-55-5462' not in result.transformed_content

    async def test_placeholder_ssns_are_deliberately_ignored(self, adapter):
        """Presidio invalidates famous fake SSNs, and that is correct.

        123-45-6789 is the canonical example value; firing on it would mean
        redacting documentation, test fixtures and sample payloads. Recorded
        as a test so nobody 'fixes' a future failure by reaching for it.
        """
        result = await adapter.evaluate(req('his ssn is 123-45-6789'))

        assert result.action is PolicyAction.ALLOW

    async def test_redacts_multiple_entities_in_one_pass(self, adapter):
        result = await adapter.evaluate(req('reach bob@corp.com or call 415-555-0142'))

        assert 'bob@corp.com' not in result.transformed_content
        assert '415-555-0142' not in result.transformed_content


class TestFalsePositives:
    async def test_ordinary_business_prompt_is_untouched(self, adapter):
        """The default entity set must not mangle normal traffic.

        Presidio's full recogniser set flags PERSON, LOCATION and DATE_TIME,
        which would turn this into "...in <LOCATION> on <DATE_TIME>". A
        guardrail that rewrites ordinary prompts gets switched off, so those
        recognisers are opt-in.
        """
        text = 'What was the weather in London on Monday, and did Sarah attend?'

        result = await adapter.evaluate(req(text))

        assert result.action is PolicyAction.ALLOW

    async def test_person_names_are_opt_in(self, adapter):
        text = 'Ask Margaret Hamilton about the guidance computer.'

        default = await adapter.evaluate(req(text))
        opted_in = await adapter.evaluate(req(text, entities=['PERSON']))

        assert default.action is PolicyAction.ALLOW
        assert opted_in.action is PolicyAction.TRANSFORM

    async def test_clean_text_is_allowed(self, adapter):
        result = await adapter.evaluate(req('summarise the quarterly report'))

        assert result.action is PolicyAction.ALLOW
        assert result.transformed_content is None


class TestConfiguration:
    async def test_entities_can_be_narrowed_by_policy(self, adapter):
        text = 'mail alice@example.com or call 415-555-0142'

        result = await adapter.evaluate(req(text, entities=['EMAIL_ADDRESS']))

        assert 'alice@example.com' not in result.transformed_content
        # Phone was not requested, so it survives.
        assert '415-555-0142' in result.transformed_content

    async def test_score_threshold_is_forwarded_to_the_analyzer(self, adapter):
        # Above the maximum possible score, so this asserts the knob is wired
        # without encoding any assumption about a recogniser's calibration.
        text = 'mail me at alice@example.com'

        result = await adapter.evaluate(req(text, score_threshold=1.01))

        assert result.action is PolicyAction.ALLOW

    async def test_default_config_catches_more_than_just_email(self, adapter):
        """The regression that mattered.

        With an invented 0.5 floor, EMAIL_ADDRESS was the only default entity
        that ever fired - it scores 1.0, while phone numbers and unvalidated
        card numbers score below the cutoff. The adapter looked like it was
        working while passing most PII straight through.
        """
        text = (
            'reach alice@example.com or 415-555-0142, '
            'ssn 457-55-5462, card 4111 1111 1111 1111'
        )

        result = await adapter.evaluate(req(text))

        found = set(result.provider_metadata['entity_types'])
        assert {'EMAIL_ADDRESS', 'PHONE_NUMBER', 'US_SSN', 'CREDIT_CARD'} <= found
        for secret in ('alice@example.com', '415-555-0142', '457-55-5462', '4111'):
            assert secret not in result.transformed_content

    async def test_default_threshold_defers_to_presidio(self):
        """Regression guard on the constant itself."""
        from flo_ai.guardrails.adapters.presidio_adapter import (
            DEFAULT_SCORE_THRESHOLD,
        )

        assert DEFAULT_SCORE_THRESHOLD == 0.0

    async def test_default_entities_are_pattern_based(self):
        """Keeps the small spaCy model sufficient for the default policy."""
        assert 'PERSON' not in DEFAULT_ENTITIES
        assert 'LOCATION' not in DEFAULT_ENTITIES
        assert 'DATE_TIME' not in DEFAULT_ENTITIES
        assert 'EMAIL_ADDRESS' in DEFAULT_ENTITIES


class TestContract:
    async def test_non_text_content_is_rejected_not_allowed(self, adapter):
        result = await adapter.evaluate(req({'not': 'text'}))

        assert result.action is PolicyAction.BLOCK
        assert result.failure_class is FailureClass.INPUT_REJECTED

    async def test_empty_content_is_allowed(self, adapter):
        result = await adapter.evaluate(req('   '))

        assert result.action is PolicyAction.ALLOW

    async def test_metadata_reports_types_and_counts_only(self, adapter):
        result = await adapter.evaluate(req('mail alice@example.com now'))

        metadata = result.provider_metadata
        assert metadata['entity_types'] == ['EMAIL_ADDRESS']
        assert metadata['entity_counts'] == {'EMAIL_ADDRESS': 1}
        assert 'alice@example.com' not in str(metadata)

    async def test_engines_are_built_once(self, adapter):
        await adapter.evaluate(req('first call'))
        first = adapter._analyzer

        await adapter.evaluate(req('second call'))

        assert adapter._analyzer is first, 'spaCy load must not repeat per request'
