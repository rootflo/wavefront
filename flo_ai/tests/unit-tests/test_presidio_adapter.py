"""Presidio adapter against the real engine.

Presidio runs in-process, so unlike the Azure adapter this needs no
credentials - only the optional extra:

    uv sync --extra guardrails
    uv run python -m spacy download en_core_web_lg

Skipped entirely when the extra is not installed.
"""

import pytest

from flo_ai.guardrails.adapters.presidio_adapter import (
    DEFAULT_ENTITIES,
    PresidioAdapter,
)
from flo_ai.guardrails.adapters.pii_catalog import (
    ENTITY_CATALOG,
    INCREMENTAL_SAFE,
    NLP_BACKED,
    UNBOUNDED_LENGTH,
)
from flo_ai.guardrails.contracts import (
    AssessmentRequest,
    EvaluationContext,
    FailureClass,
    PolicyAction,
    Principal,
    StreamCapability,
    WorkflowStage,
)
from flo_ai.guardrails.stream_guard import DEFAULT_MARGIN_CHARS

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
        result = await adapter.evaluate(
            req('mail me at alice@example.com please', entities=['EMAIL_ADDRESS'])
        )

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
        result = await adapter.evaluate(
            req('his ssn is 457-55-5462', entities=['US_SSN'])
        )

        assert result.action is PolicyAction.TRANSFORM
        assert '457-55-5462' not in result.transformed_content

    async def test_placeholder_ssns_are_deliberately_ignored(self, adapter):
        """Presidio invalidates famous fake SSNs, and that is correct.

        123-45-6789 is the canonical example value; firing on it would mean
        redacting documentation, test fixtures and sample payloads. Recorded
        as a test so nobody 'fixes' a future failure by reaching for it.
        """
        result = await adapter.evaluate(
            req('his ssn is 123-45-6789', entities=['US_SSN'])
        )

        assert result.action is PolicyAction.ALLOW

    async def test_redacts_multiple_entities_in_one_pass(self, adapter):
        result = await adapter.evaluate(
            req(
                'reach bob@corp.com or call 415-555-0142',
                entities=['EMAIL_ADDRESS', 'PHONE_NUMBER'],
            )
        )

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

    async def test_threshold_keeps_the_identifiers_that_matter(self, adapter):
        """The regression that mattered.

        With an invented 0.5 floor, EMAIL_ADDRESS was the only entity that ever
        fired - it scores 1.0, while a phone number scores 0.4. The adapter
        looked like it was working while passing most PII straight through.
        The default floor must stay below every one of these.
        """
        text = (
            'reach alice@example.com or 415-555-0142, '
            'ssn 457-55-5462, card 4111 1111 1111 1111'
        )

        result = await adapter.evaluate(
            req(
                text,
                entities=[
                    'EMAIL_ADDRESS',
                    'PHONE_NUMBER',
                    'US_SSN',
                    'CREDIT_CARD',
                ],
            )
        )

        found = set(result.provider_metadata['entity_types'])
        assert {'EMAIL_ADDRESS', 'PHONE_NUMBER', 'US_SSN', 'CREDIT_CARD'} <= found
        for secret in ('alice@example.com', '415-555-0142', '457-55-5462', '4111'):
            assert secret not in result.transformed_content

    async def test_default_threshold_excludes_shape_only_noise(self, adapter):
        """An order number must not be mistaken for three identifiers at once.

        Nine bare digits match US_SSN, US_BANK_NUMBER and US_PASSPORT
        simultaneously, each scoring 0.05 because nothing in the sentence
        supports the guess. The default floor is what keeps them out.
        """
        result = await adapter.evaluate(
            req(
                'Order #234567890 shipped Monday',
                entities=['US_SSN', 'US_BANK_NUMBER', 'US_PASSPORT'],
            )
        )

        assert result.action is PolicyAction.ALLOW

    async def test_context_still_promotes_a_bare_identifier(self, adapter):
        """The floor must not cost us identifiers Presidio infers from context.

        The same nine digits are boosted from 0.05 to 0.4 by the neighbouring
        word, which is the whole reason the floor sits at 0.3 and not higher.
        """
        result = await adapter.evaluate(
            req('his ssn is 457555462', entities=['US_SSN'])
        )

        assert result.action is PolicyAction.TRANSFORM

    async def test_default_threshold_is_pinned(self):
        """Regression guard on the constant itself."""
        from flo_ai.guardrails.adapters.presidio_adapter import (
            DEFAULT_SCORE_THRESHOLD,
        )

        assert DEFAULT_SCORE_THRESHOLD == 0.3

    async def test_defaults_are_conservative(self):
        """Nothing country-specific, and nothing model-inferred, by default.

        A namespace nobody has configured should redact only what can be
        verified outright, so enabling guardrails cannot start rewriting
        ordinary traffic.
        """
        assert tuple(DEFAULT_ENTITIES) == ('CREDIT_CARD',)


class TestContract:
    async def test_non_text_content_is_rejected_not_allowed(self, adapter):
        result = await adapter.evaluate(req({'not': 'text'}))

        assert result.action is PolicyAction.BLOCK
        assert result.failure_class is FailureClass.INPUT_REJECTED

    async def test_empty_content_is_allowed(self, adapter):
        result = await adapter.evaluate(req('   '))

        assert result.action is PolicyAction.ALLOW

    async def test_metadata_reports_types_and_counts_only(self, adapter):
        result = await adapter.evaluate(
            req('mail alice@example.com now', entities=['EMAIL_ADDRESS'])
        )

        metadata = result.provider_metadata
        assert metadata['entity_types'] == ['EMAIL_ADDRESS']
        assert metadata['entity_counts'] == {'EMAIL_ADDRESS': 1}
        assert 'alice@example.com' not in str(metadata)

    async def test_engines_are_built_once(self, adapter):
        await adapter.evaluate(req('first call'))
        first = adapter._analyzer

        await adapter.evaluate(req('second call'))

        assert adapter._analyzer is first, 'spaCy load must not repeat per request'


class TestEntitySelection:
    """The console writes `options['entities']`, so these guard the wiring."""

    async def test_absent_entities_uses_the_default_set(self, adapter):
        """Every policy stored before entity selection existed omits the key."""
        text = 'mail alice@example.com or call 415-555-0142'

        implicit = await adapter.evaluate(req(text))
        explicit = await adapter.evaluate(req(text, entities=list(DEFAULT_ENTITIES)))

        assert implicit.transformed_content == explicit.transformed_content

    async def test_empty_selection_runs_no_checks(self, adapter):
        """An explicit empty list must not mean "detect everything".

        Presidio treats a falsy entity list as all_fields=True, so clearing
        every checkbox would switch on PERSON, LOCATION and DATE_TIME and
        redact ordinary prose - the opposite of what clearing them asks for.
        """
        result = await adapter.evaluate(
            req('mail alice@example.com on Monday in London', entities=[])
        )

        assert result.action is PolicyAction.ALLOW
        assert result.transformed_content is None

    async def test_unknown_entity_is_a_misconfiguration_not_an_outage(self, adapter):
        """Presidio raises when nothing serves the request.

        Left to escape, that is classified INFRASTRUCTURE, which honours
        FAIL_OPEN - so a fail-open policy would run no PII checks at all while
        the console still read as enforced.
        """
        result = await adapter.evaluate(
            req('mail alice@example.com', entities=['NOT_A_REAL_ENTITY'])
        )

        assert result.action is PolicyAction.BLOCK
        assert result.failure_class is FailureClass.MISCONFIGURED

    async def test_unselected_types_pass_through(self, adapter):
        """The point of the feature: allow email, redact the card."""
        text = 'mail alice@example.com, card 4111 1111 1111 1111'

        result = await adapter.evaluate(req(text, entities=['CREDIT_CARD']))

        assert 'alice@example.com' in result.transformed_content
        assert '4111' not in result.transformed_content


class TestOptionalRecognisers:
    """Presidio ships the country packs disabled; the adapter loads them."""

    async def test_country_entities_are_available(self, adapter):
        supported = await adapter.supported_entities()

        # A default AnalyzerEngine reports 19 entity types and none of these.
        assert 'IN_AADHAAR' in supported
        assert 'UK_NINO' in supported
        assert 'CA_SIN' in supported

    async def test_aadhaar_checksum_is_enforced(self, adapter):
        """Verhoeff-validated, so ordinary 12-digit numbers are not flagged."""
        valid = await adapter.evaluate(
            req('aadhaar 234123412346 on file', entities=['IN_AADHAAR'])
        )
        invalid = await adapter.evaluate(
            req('order 123456789012 shipped', entities=['IN_AADHAAR'])
        )

        assert valid.action is PolicyAction.TRANSFORM
        assert '234123412346' not in valid.transformed_content
        assert invalid.action is PolicyAction.ALLOW

    async def test_loading_them_does_not_change_default_behaviour(self, adapter):
        """Registering a recogniser must not make it fire.

        Existing namespaces store no entity selection, so nothing new may be
        detected for them - otherwise this change starts redacting traffic
        nobody opted in to.
        """
        result = await adapter.evaluate(req('aadhaar 234123412346 and NINO QQ123456C'))

        types = set(result.provider_metadata.get('entity_types') or ())
        assert 'IN_AADHAAR' not in types
        assert 'UK_NINO' not in types

    async def test_precision_is_derived_from_the_registry(self, adapter):
        precision = await adapter.entity_precision()

        # Checksum-validated, pattern-only, and language-model-backed.
        assert precision['IN_AADHAAR']['precision'] == 'validated'
        assert precision['IN_PAN']['precision'] == 'pattern'
        assert precision['PERSON']['precision'] == 'nlp'


class TestRedactionStyle:
    async def test_keep_last_preserves_the_tail_across_lengths(self, adapter):
        """One operator map spans entities of differing length.

        Presidio's own `mask` operator takes an absolute character count, so a
        single setting cannot mean "keep the last four" for both a 16-digit
        card and a 10-digit phone number.
        """
        result = await adapter.evaluate(
            req(
                'card 4111 1111 1111 1111 phone 415-555-0142',
                entities=['CREDIT_CARD', 'PHONE_NUMBER'],
                operators={
                    'CREDIT_CARD': {'type': 'mask', 'keep_last': 4},
                    'PHONE_NUMBER': {'type': 'mask', 'keep_last': 4},
                },
            )
        )

        assert result.transformed_content.endswith('0142')
        assert '1111 1111 1111' not in result.transformed_content
        assert '415-555' not in result.transformed_content

    async def test_keep_last_longer_than_the_match_masks_everything(self, adapter):
        """The leak guard: a short value must not pass through verbatim."""
        result = await adapter.evaluate(
            req(
                'host 1.2.3.4 responded',
                entities=['IP_ADDRESS'],
                operators={'IP_ADDRESS': {'type': 'mask', 'keep_last': 8}},
            )
        )

        assert '1.2.3.4' not in result.transformed_content

    async def test_hash_replaces_with_an_opaque_token(self, adapter):
        result = await adapter.evaluate(
            req(
                'mail alice@example.com',
                entities=['EMAIL_ADDRESS'],
                operators={'EMAIL_ADDRESS': {'type': 'hash'}},
            )
        )

        assert 'alice@example.com' not in result.transformed_content
        assert '<EMAIL_ADDRESS>' not in result.transformed_content

    async def test_default_style_uses_the_bracket_placeholder(self, adapter):
        """With no operators configured, the default is [ENTITY], not <ENTITY>.

        This assertion used to pin Presidio's own ``<ENTITY_TYPE>`` output.
        That default is unusable here: ``resolve_variables`` treats ``<NAME>``
        as a template variable and raises on any it cannot resolve, so a
        redaction written into conversation history broke every later turn.
        See PLACEHOLDER_FORMAT in the adapter.
        """
        result = await adapter.evaluate(
            req('mail alice@example.com', entities=['EMAIL_ADDRESS'])
        )

        assert '[EMAIL_ADDRESS]' in result.transformed_content
        assert '<EMAIL_ADDRESS>' not in result.transformed_content
        assert 'alice@example.com' not in result.transformed_content


class TestAllowList:
    async def test_exact_terms_are_never_redacted(self, adapter):
        result = await adapter.evaluate(
            req(
                'write to support@acme.com not alice@example.com',
                entities=['EMAIL_ADDRESS'],
                allow_list=['support@acme.com'],
            )
        )

        assert 'support@acme.com' in result.transformed_content
        assert 'alice@example.com' not in result.transformed_content


class TestPreview:
    async def test_reports_spans_for_the_console(self, adapter):
        result = await adapter.preview(
            'mail alice@example.com', {'entities': ['EMAIL_ADDRESS']}
        )

        assert result['findings'][0]['entity_type'] == 'EMAIL_ADDRESS'
        assert 'alice@example.com' not in result['redacted_text']
        # Offsets locate the match without the response carrying the value.
        span = result['findings'][0]
        assert 'mail alice@example.com'[span['start'] : span['end']] == (
            'alice@example.com'
        )

    async def test_empty_selection_reports_nothing(self, adapter):
        result = await adapter.preview('mail alice@example.com', {'entities': []})

        assert result['findings'] == []
        assert result['redacted_text'] == 'mail alice@example.com'


class TestPlaceholderFormat:
    """Redaction output must survive flo_ai's own variable templating."""

    async def test_placeholder_does_not_look_like_a_template_variable(self):
        """Regression: <ENTITY> redaction poisoned the conversation.

        ``resolve_variables`` substitutes ``<name>`` and raises on anything it
        cannot resolve, and it runs over the whole conversation history every
        turn. Presidio's default ``<CREDIT_CARD>`` therefore became an
        unresolvable variable as soon as an AFTER_MODEL redaction was written
        to history, and every subsequent turn failed with "Variable
        'CREDIT_CARD' referenced in text but not provided" until the
        conversation was abandoned.
        """
        from flo_ai.utils.variable_extractor import resolve_variables

        adapter = PresidioAdapter(entities=['CREDIT_CARD', 'EMAIL_ADDRESS'])
        result = await adapter.evaluate(req('card 4111 1111 1111 1111 mail a@b.com'))
        redacted = result.transformed_content

        assert '[CREDIT_CARD]' in redacted
        assert '<CREDIT_CARD>' not in redacted
        # The actual guarantee: a later turn can still resolve this text.
        assert resolve_variables(redacted, {}) == redacted
        await adapter.aclose()


class TestStreamCapability:
    """Which selections may be released incrementally, and which may not.

    Pure option inspection -- no analyzer is built, so these run whether or
    not the optional extra is installed.
    """

    def test_span_local_findings_are_the_class_default(self):
        assert PresidioAdapter.stream_capability is StreamCapability.INCREMENTAL

    def test_a_bounded_identifier_streams(self):
        adapter = PresidioAdapter()

        capability = adapter.stream_capability_for({'entities': ['CREDIT_CARD']})

        assert capability is StreamCapability.INCREMENTAL

    def test_an_nlp_backed_entity_buffers(self):
        """PERSON needs a parsed sentence and has no length bound."""
        adapter = PresidioAdapter()

        capability = adapter.stream_capability_for({'entities': ['PERSON']})

        assert capability is StreamCapability.BUFFERED

    def test_url_buffers(self):
        """Unbounded length defeats the margin the guarantee rests on."""
        adapter = PresidioAdapter()

        capability = adapter.stream_capability_for({'entities': ['URL']})

        assert capability is StreamCapability.BUFFERED

    def test_one_unsafe_entity_decides_for_the_selection(self):
        adapter = PresidioAdapter()

        capability = adapter.stream_capability_for(
            {'entities': ['CREDIT_CARD', 'US_SSN', 'URL']}
        )

        assert capability is StreamCapability.BUFFERED

    def test_an_unset_selection_falls_back_to_the_defaults(self):
        """DEFAULT_ENTITIES is CREDIT_CARD, so an unconfigured policy streams."""
        adapter = PresidioAdapter()

        assert adapter.stream_capability_for({}) is StreamCapability.INCREMENTAL

    def test_selecting_nothing_is_vacuously_safe(self):
        """An empty list means detect nothing, so there is nothing to leak."""
        adapter = PresidioAdapter()

        capability = adapter.stream_capability_for({'entities': []})

        assert capability is StreamCapability.INCREMENTAL

    def test_a_hash_operator_buffers(self):
        """Hashing expands to 64 hex characters, outrunning the plaintext cut."""
        adapter = PresidioAdapter()

        capability = adapter.stream_capability_for(
            {
                'entities': ['CREDIT_CARD'],
                'operators': {'CREDIT_CARD': {'type': 'hash'}},
            }
        )

        assert capability is StreamCapability.BUFFERED

    def test_a_masking_operator_still_streams(self):
        adapter = PresidioAdapter()

        capability = adapter.stream_capability_for(
            {
                'entities': ['CREDIT_CARD'],
                'operators': {'CREDIT_CARD': {'type': 'mask'}},
            }
        )

        assert capability is StreamCapability.INCREMENTAL


class TestAllowlistInvariants:
    """The allowlist and the margin are one mechanism in two files.

    These assertions are the reminder that editing either means re-checking
    the other, which a comment alone would not enforce.
    """

    def test_the_allowlist_excludes_everything_unbounded(self):
        assert INCREMENTAL_SAFE.isdisjoint(UNBOUNDED_LENGTH)
        assert INCREMENTAL_SAFE.isdisjoint(NLP_BACKED)

    def test_the_margin_covers_the_longest_allowlisted_entity(self):
        """EMAIL_ADDRESS at the RFC 5321 maximum is the binding constraint."""
        assert 'EMAIL_ADDRESS' in INCREMENTAL_SAFE
        assert DEFAULT_MARGIN_CHARS >= 320

    def test_the_allowlist_is_derived_rather_than_typed_out(self):
        """An entity the catalog has never heard of must not stream.

        This is what makes staleness cost latency rather than a guarantee: a
        new recogniser arriving with a Presidio upgrade is absent from the
        catalog, so absent from here, so a policy selecting it buffers.
        """
        assert INCREMENTAL_SAFE <= frozenset(ENTITY_CATALOG)
