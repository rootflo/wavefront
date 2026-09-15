"""Local PII detection and redaction via Microsoft Presidio."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Sequence

from flo_ai.utils.logger import logger

from ..contracts import (
    AssessmentRequest,
    AssessmentStatus,
    CheckResult,
    FailureClass,
    PolicyAction,
)
from .base_adapter import BaseAdapter
from .pii_catalog import NLP_BACKED

#: What runs when a policy names no entity types.
#:
#: One entry, and a deliberately conservative one. Card numbers are Luhn
#: checked, so this fires on real cards and almost nothing else — it is the
#: only entity that is safe to switch on for a namespace nobody has configured.
#:
#: Everything else is opt-in, for two reasons. Presidio's NLP-backed entities
#: (PERSON, LOCATION, DATE_TIME, NRP) fire constantly on ordinary business
#: prompts — "What's the weather in London on Monday?" comes back as "...in
#: <LOCATION> on <DATE_TIME>". And most country identifiers are shape-only
#: patterns with no checksum, so several claim the same digits at once: a
#: nine-digit order number matches US_BANK_NUMBER, US_PASSPORT and US_SSN
#: together. Either way a guardrail that mangles normal traffic gets switched
#: off, which protects nothing.
#:
#: Country-specific types are therefore never on by default; an operator picks
#: the ones their jurisdiction needs.
DEFAULT_ENTITIES: Sequence[str] = ('CREDIT_CARD',)

#: Drop matches Presidio itself is barely confident in.
#:
#: Presidio scores each match and then boosts it when nearby words support the
#: guess, which separates real identifiers from lookalikes far more sharply
#: than the raw patterns do. Measured against presidio-analyzer 2.2.364:
#:
#:     email / card / IBAN / Aadhaar        1.0
#:     US SSN, dashed or spaced             0.85
#:     phone number                         0.4
#:     bare 9 digits next to the word "ssn" 0.4   (boosted from 0.05)
#:     "Order #234567890"                   0.05  US_SSN, US_BANK_NUMBER
#:                                          0.05  and US_PASSPORT, all at once
#:
#: 0.3 sits in the gap. Everything above it is an identifier something actually
#: vouched for; everything below is shape alone. Without a floor, any nine-digit
#: order number is redacted three times over, because several shape-only
#: recognisers claim it simultaneously - and a guardrail that mangles ordinary
#: traffic gets switched off, which protects nothing.
#:
#: An earlier 0.5 was too aggressive: it discards phone numbers and any SSN
#: recognised only from context. A policy can still override this per namespace
#: through the ``score_threshold`` option.
DEFAULT_SCORE_THRESHOLD = 0.3

#: Redaction styles a policy may name, mapped to a Presidio operator.
#:
#: ``keep_last`` is deliberately absent from this map — it cannot be expressed
#: as a stock operator; see :func:`_keep_last`.
_SIMPLE_OPERATORS = {'replace', 'redact', 'hash'}

#: Redaction placeholder format. Braces, not the angle brackets Presidio
#: defaults to.
#:
#: ``flo_ai.utils.variable_extractor.resolve_variables`` substitutes ``<name>``
#: template variables and **raises** on any it cannot resolve. It runs over
#: every message in the conversation history on every turn, so a Presidio
#: default of ``<CREDIT_CARD>`` becomes an unresolvable variable the moment a
#: redaction lands in history: the next turn dies with "Variable 'CREDIT_CARD'
#: referenced in text but not provided", retries, and the conversation is
#: permanently unusable.
#:
#: Square brackets are the conventional redaction marker and collide with no
#: templating syntax in this SDK.
PLACEHOLDER_FORMAT = '[{entity}]'

#: Sentinel distinguishing "policy did not mention entities" from "policy
#: explicitly selected none". The two must not collapse: the first means
#: DEFAULT_ENTITIES, the second means run nothing.
_UNSET = object()

#: Recognisers never loaded by :meth:`PresidioAdapter._augment_registry`.
#:
#: These are model- or network-backed rather than pattern-backed. They fail to
#: construct today because their optional dependency is absent, but relying on
#: that is fragile: installing ``transformers`` for something unrelated would
#: otherwise silently start loading a NER model into every guarded request.
_SKIP_RECOGNIZERS = frozenset(
    {
        'AzureAILanguageRecognizer',
        'AzureOpenAILangExtractRecognizer',
        'BasicLangExtractRecognizer',
        'GLiNERRecognizer',
        'HuggingFaceNerRecognizer',
        'LangExtractRecognizer',
        'MedicalNerRecognizer',
        'AHDSRecognizer',
    }
)

_IMPORT_HINT = (
    'Presidio is not installed. Install the guardrails extra:\n'
    "    pip install 'flo_ai[guardrails]'\n"
    'and download a spaCy model:\n'
    '    python -m spacy download en_core_web_lg'
)


def _keep_last(keep: int, masking_char: str = '*'):
    """Mask everything but the trailing ``keep`` characters.

    Presidio's ``mask`` operator cannot express this. It takes an absolute
    ``chars_to_mask`` which it clamps with ``min(len(text), chars_to_mask)``,
    so a single policy value cannot mean "keep the last four" across entities
    of differing length: ``chars_to_mask=12`` keeps the last four digits of a
    16-digit card but masks a 10-digit phone number in full.

    Values shorter than ``keep`` are masked entirely rather than passed
    through — otherwise a short match would be emitted verbatim, which is the
    one outcome redaction exists to prevent.
    """

    def operate(value: str) -> str:
        if len(value) <= keep:
            return masking_char * len(value)
        return masking_char * (len(value) - keep) + value[-keep:]

    return operate


class PresidioAdapter(BaseAdapter):
    """Detects and redacts PII in-process.

    Being local matters for the failure story: when a remote provider is
    unreachable the deployment degrades to this rather than to nothing, which
    is what makes fail-open on the remote adapter defensible.
    """

    def __init__(
        self,
        entities: Optional[Sequence[str]] = None,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
        language: str = 'en',
        max_workers: int = 2,
        load_optional_recognizers: bool = True,
    ) -> None:
        self._entities = list(entities) if entities else list(DEFAULT_ENTITIES)
        self._score_threshold = score_threshold
        self._language = language
        self._load_optional_recognizers = load_optional_recognizers
        self._analyzer: Any = None
        self._anonymizer: Any = None
        self._init_lock = asyncio.Lock()
        # spaCy analysis is CPU-heavy and would otherwise contend with every
        # other to_thread caller on the default executor.
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix='presidio'
        )

    @property
    def name(self) -> str:
        return 'presidio_pii'

    async def aclose(self) -> None:
        self._executor.shutdown(wait=False)

    async def _engines(self) -> tuple:
        """Build the Presidio engines once, off the event loop.

        Construction loads a spaCy model and takes seconds, so it must not
        happen in ``__init__`` (which runs on the loop) nor per request.
        """
        if self._analyzer is not None:
            return self._analyzer, self._anonymizer

        async with self._init_lock:
            if self._analyzer is not None:
                return self._analyzer, self._anonymizer

            def _build() -> tuple:
                try:
                    from presidio_analyzer import AnalyzerEngine
                    from presidio_anonymizer import AnonymizerEngine
                except ImportError as exc:  # pragma: no cover - env dependent
                    raise RuntimeError(_IMPORT_HINT) from exc
                analyzer = AnalyzerEngine()
                if self._load_optional_recognizers:
                    self._augment_registry(analyzer)
                return analyzer, AnonymizerEngine()

            loop = asyncio.get_running_loop()
            analyzer, anonymizer = await loop.run_in_executor(self._executor, _build)
            self._analyzer, self._anonymizer = analyzer, anonymizer
            logger.debug('Presidio engines initialised')

        return self._analyzer, self._anonymizer

    def _augment_registry(self, analyzer: Any) -> None:
        """Load the country recognisers Presidio ships but leaves switched off.

        A default ``AnalyzerEngine`` covers 19 entity types. Presidio's
        ``default_recognizers.yaml`` lists 74 and marks 50 of them
        ``enabled: false`` — among them the entire India pack (Aadhaar, PAN,
        GSTIN, voter ID), the UK pack, Canada, Singapore, Australia and South
        Africa. Without this, offering those entity types in the console would
        be offering checkboxes that detect nothing, and selecting one would
        raise ``No matching recognizers`` and fail the namespace closed.

        Presidio's own loader cannot enable them: it forwards the YAML ``name``
        key into the recogniser constructor, and the disabled classes do not
        accept ``name``, so flipping the flag raises ``TypeError``. They are
        therefore instantiated directly.

        This is inert for existing policies. Every added recogniser serves only
        entities the engine did not already cover, and a recogniser is only
        consulted when its entity is named in ``analyze(entities=...)`` — which
        ``_resolve_entities`` guarantees is never empty. Nothing new fires until
        an admin selects it.
        """
        try:
            import os

            import yaml

            import presidio_analyzer
            import presidio_analyzer.predefined_recognizers as predefined
        except Exception as exc:  # pragma: no cover - env dependent
            logger.warning(f'Presidio: optional recognisers unavailable ({exc})')
            return

        conf_path = os.path.join(
            os.path.dirname(presidio_analyzer.__file__),
            'conf',
            'default_recognizers.yaml',
        )
        try:
            with open(conf_path) as handle:
                parsed = yaml.safe_load(handle)
        except Exception as exc:
            logger.warning(
                f'Presidio: could not read {conf_path} ({exc}); '
                'country recognisers stay disabled'
            )
            return

        entries = parsed.get('recognizers') if isinstance(parsed, dict) else parsed
        if not isinstance(entries, list):
            logger.warning('Presidio: unexpected recogniser config shape')
            return

        registry = analyzer.registry
        covered = {
            entity
            for recognizer in registry.recognizers
            if recognizer.supported_language == self._language
            for entity in recognizer.supported_entities
        }

        added: List[str] = []
        skipped: List[str] = []
        for entry in entries:
            if not isinstance(entry, dict) or entry.get('enabled') is not False:
                continue
            name = entry.get('name')
            if not name or name in _SKIP_RECOGNIZERS:
                continue

            recognizer_cls = getattr(predefined, name, None)
            if recognizer_cls is None:
                skipped.append(name)
                continue
            try:
                instance = recognizer_cls()
            except Exception as exc:
                # Optional dependency, or an upstream signature change. Either
                # way one recogniser must not stop the engine from starting.
                skipped.append(f'{name}({type(exc).__name__})')
                continue

            if instance.supported_language != self._language:
                continue
            # Never shadow a recogniser that is already loaded: two recognisers
            # for one entity means duplicate findings and unpredictable scores.
            if set(instance.supported_entities) & covered:
                continue

            registry.add_recognizer(instance)
            covered.update(instance.supported_entities)
            added.append(name)

        logger.info(
            f'Presidio: loaded {len(added)} optional recognisers, '
            f'{len(covered)} entity types available'
            + (f'; unavailable: {", ".join(skipped)}' if skipped else '')
        )

    # -- policy translation ----------------------------------------------

    def _resolve_entities(self, options: Dict[str, Any]) -> Optional[List[str]]:
        """Which entity types this policy wants detected.

        Returns ``None`` for "the policy selected nothing", which the caller
        turns into a clean allow. That case must not reach Presidio: passing an
        empty list to ``analyze`` sets ``all_fields=True``, so clearing every
        checkbox in the console would switch on PERSON, LOCATION and DATE_TIME
        and redact ordinary prose — the exact opposite of what was asked.
        """
        configured = options.get('entities', _UNSET)
        if configured is _UNSET or configured is None:
            return list(self._entities)
        if not configured:
            return None
        return list(configured)

    def _operators(
        self, options: Dict[str, Any], detected: Optional[Sequence[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Per-entity redaction style, as Presidio operator configs.

        Every detected entity gets an explicit placeholder rather than falling
        through to Presidio's ``<ENTITY>`` default, for the reason given on
        :data:`PLACEHOLDER_FORMAT`. Policy-configured operators override it.
        """
        from presidio_anonymizer import OperatorConfig

        configured = options.get('operators') or {}

        operators: Dict[str, Any] = {
            entity: OperatorConfig(
                'replace', {'new_value': PLACEHOLDER_FORMAT.format(entity=entity)}
            )
            for entity in detected or ()
        }
        for entity, spec in configured.items():
            if not isinstance(spec, dict):
                continue
            style = spec.get('type') or 'replace'

            if style == 'mask':
                keep = int(spec.get('keep_last', 4))
                char = str(spec.get('masking_char') or '*')[:1] or '*'
                operators[entity] = OperatorConfig(
                    'custom', {'lambda': _keep_last(keep, char)}
                )
            elif style == 'replace':
                new_value = spec.get('new_value') or PLACEHOLDER_FORMAT.format(
                    entity=entity
                )
                operators[entity] = OperatorConfig(
                    'replace', {'new_value': str(new_value)}
                )
            elif style in _SIMPLE_OPERATORS:
                operators[entity] = OperatorConfig(style)
            else:
                logger.warning(
                    f'Guardrails: unknown redaction style {style!r} for '
                    f'{entity}, falling back to replace'
                )

        return operators or None

    # -- evaluation ------------------------------------------------------

    async def evaluate(self, request: AssessmentRequest) -> CheckResult:
        if not isinstance(request.content, str):
            # Caller-controlled shape, so this must not be a silent pass.
            return self._error(
                FailureClass.INPUT_REJECTED,
                'Presidio only evaluates text content',
                finding_code='guardrail.unsupported_content',
            )

        text = request.content
        if not text.strip():
            return self._allow()

        entities = self._resolve_entities(request.options)
        if entities is None:
            return self._allow()

        try:
            findings = await self._analyze(text, entities, request.options)
        except ValueError as exc:
            # Presidio raises when no registered recogniser serves any of the
            # requested entities. That is a policy error, not an outage, and
            # classifying it as INFRASTRUCTURE would let a FAIL_OPEN policy
            # quietly run no checks at all while the console still reads as
            # enforced. MISCONFIGURED always stays closed.
            return self._error(
                FailureClass.MISCONFIGURED,
                f'No PII recogniser is available for the selected entity '
                f'types: {", ".join(entities)} ({exc})',
                finding_code='guardrail.misconfigured',
            )

        if not findings:
            return self._allow()

        anonymized = await self._anonymize(text, findings, request.options)

        entity_types = sorted({f.entity_type for f in findings})
        return CheckResult(
            status=AssessmentStatus.VIOLATION,
            action=PolicyAction.TRANSFORM,
            adapter=self.name,
            finding_code='privacy.pii_detected',
            message=f'Redacted {len(findings)} PII entities: {", ".join(entity_types)}',
            transformed_content=anonymized.text,
            severity=max((f.score for f in findings), default=None),
            # Entity *types* and counts only - never the matched values.
            provider_metadata=self._metadata(findings, entity_types),
        )

    async def _analyze(
        self, text: str, entities: List[str], options: Dict[str, Any]
    ) -> List[Any]:
        threshold = float(options.get('score_threshold', self._score_threshold))
        language = options.get('language') or self._language
        allow_list = list(options.get('allow_list') or ())
        allow_list_match = options.get('allow_list_match') or 'exact'

        analyzer, _ = await self._engines()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: analyzer.analyze(
                text=text,
                language=language,
                entities=entities,
                score_threshold=threshold,
                allow_list=allow_list,
                allow_list_match=allow_list_match,
            ),
        )

    async def _anonymize(
        self, text: str, findings: List[Any], options: Dict[str, Any]
    ) -> Any:
        _, anonymizer = await self._engines()
        operators = self._operators(options, detected={f.entity_type for f in findings})
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: anonymizer.anonymize(
                text=text, analyzer_results=findings, operators=operators
            ),
        )

    # -- console support -------------------------------------------------

    async def supported_entities(self, language: Optional[str] = None) -> List[str]:
        """Entity types this deployment's recogniser set can actually produce.

        Asked of the running engine rather than read from a constant, so the
        settings page cannot offer a checkbox that silently detects nothing.
        """
        analyzer, _ = await self._engines()
        lang = language or self._language
        loop = asyncio.get_running_loop()
        entities = await loop.run_in_executor(
            self._executor, lambda: analyzer.get_supported_entities(language=lang)
        )
        return sorted(entities)

    async def entity_precision(
        self, language: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """How trustworthy each entity's detection is, derived from the registry.

        Entities differ enormously here and the difference is invisible from
        the name alone: IN_AADHAAR runs a Verhoeff checksum and only fires on
        genuine numbers, while DE_PLZ is a bare five-digit pattern scored 0.05
        that matches any such figure. Surfacing the distinction is what stops
        an admin enabling a plausible-looking entity and drowning in false
        positives.

        Computed from the loaded recognisers rather than hand-maintained, so a
        Presidio upgrade cannot leave the labels lying.
        """
        analyzer, _ = await self._engines()
        lang = language or self._language

        def _collect() -> Dict[str, Dict[str, Any]]:
            from presidio_analyzer import PatternRecognizer

            recognizers = analyzer.registry.get_recognizers(
                language=lang, all_fields=True
            )
            out: Dict[str, Dict[str, Any]] = {}
            for recognizer in recognizers:
                patterns = getattr(recognizer, 'patterns', None) or ()
                min_score = min((p.score for p in patterns), default=None)
                is_pattern = isinstance(recognizer, PatternRecognizer)
                validates = (
                    is_pattern
                    and type(recognizer).validate_result
                    is not PatternRecognizer.validate_result
                )

                for entity in recognizer.get_supported_entities():
                    if entity in NLP_BACKED:
                        precision = 'nlp'
                    elif validates or not is_pattern:
                        # Either a checksum override, or a recogniser backed by
                        # a dedicated library (PhoneRecognizer uses
                        # phonenumbers). Both validate beyond shape.
                        precision = 'validated'
                    else:
                        precision = 'pattern'

                    # An entity can be served by several recognisers; keep the
                    # weakest, since that is what will actually fire.
                    existing = out.get(entity)
                    if existing is None or _is_weaker(precision, existing['precision']):
                        out[entity] = {
                            'precision': precision,
                            'min_pattern_score': min_score,
                        }
            return out

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _collect)

    async def preview(self, text: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """Run a draft policy against sample text and report what it would do.

        Returns match spans, which :meth:`evaluate` deliberately never does.
        The exception is justified by who is asking: an admin previewing text
        they supplied in the same request, with nothing persisted. Judging
        whether a policy is too aggressive is impossible from counts alone.
        """
        entities = self._resolve_entities(options)
        if entities is None or not text.strip():
            return {'redacted_text': text, 'findings': []}

        findings = await self._analyze(text, entities, options)
        if not findings:
            return {'redacted_text': text, 'findings': []}

        anonymized = await self._anonymize(text, findings, options)
        return {
            'redacted_text': anonymized.text,
            'findings': [
                {
                    'entity_type': f.entity_type,
                    'start': f.start,
                    'end': f.end,
                    'score': round(float(f.score), 4),
                }
                for f in sorted(findings, key=lambda f: f.start)
            ],
        }

    @staticmethod
    def _metadata(findings: List[Any], entity_types: List[str]) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for finding in findings:
            counts[finding.entity_type] = counts.get(finding.entity_type, 0) + 1
        return {'entity_counts': counts, 'entity_types': entity_types}


#: Weakest first, so a tie between two recognisers reports the looser one.
_PRECISION_RANK = {'pattern': 0, 'nlp': 1, 'validated': 2}


def _is_weaker(candidate: str, current: str) -> bool:
    return _PRECISION_RANK.get(candidate, 0) < _PRECISION_RANK.get(current, 0)
