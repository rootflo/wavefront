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
    StreamCapability,
)
from .base_adapter import BaseAdapter
from .pii_catalog import INCREMENTAL_SAFE, NLP_BACKED

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


def _swallow_result(task: 'asyncio.Future') -> None:
    """Retrieve a finished build's outcome so asyncio does not complain.

    Every caller of a build can be cancelled — the engine runs adapter calls
    under a timeout — and a task whose exception nobody reads is reported at
    shutdown as "exception was never retrieved". The real handling is in
    ``_engines``; this only stops the noise.
    """
    if not task.cancelled():
        task.exception()


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

    #: Findings are spans, so a verdict on a prefix stays true of that prefix.
    #: Narrowed per policy by ``stream_capability_for``, which is where the
    #: selections that break the span argument are turned away.
    stream_capability = StreamCapability.INCREMENTAL

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
        #: The in-flight build, so a cancelled caller cannot discard it.
        self._init_task: Optional['asyncio.Future'] = None
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

    async def warmup(self) -> None:
        """Do everything the first real check would do, now.

        See ``BaseAdapter.warmup``. Call this at startup: the alternative is
        that the first request to be checked absorbs the cost inside a
        five-second check timeout, and is rejected for it.

        Building the engines is not enough on its own. ``AnalyzerEngine()``
        loads the spaCy model, but the first ``analyze`` after that is still
        far slower than the ones following it — spaCy initialises pipeline
        components lazily, and Presidio resolves its recognisers against the
        requested entity list on the call rather than at construction. Warming
        only the constructor left a smaller version of the same cliff, still
        big enough to blow the timeout.

        So this runs a real pass over a synthetic payload, chosen to produce a
        finding so the anonymiser is exercised too rather than skipped as it is
        on clean text.
        """
        await self._engines()

        # Synthetic, and a documented test number rather than anything real:
        # this string is only ever handed to a local model.
        sample = 'card 4111111111111111'
        try:
            findings = await self._analyze(sample, list(self._entities), {})
            await self._anonymize(sample, findings, {})
        except Exception as exc:
            # A warm-up failure is not a reason to refuse to start. The
            # adapter will try again on first use, which is the behaviour
            # there was before warming existed.
            logger.warning(
                f'Presidio warm-up pass failed ({exc}). The engines are built, '
                f'but the first check may still be slow.'
            )

    async def _engines(self) -> tuple:
        """Build the Presidio engines once, off the event loop.

        Construction loads a spaCy model and takes seconds, so it must not
        happen in ``__init__`` (which runs on the loop) nor per request.

        The build is owned by a task on the instance rather than awaited
        directly, and callers wait on it through ``shield``. Both halves of
        that matter, because the engine runs every adapter call under
        ``wait_for``: a timeout cancels the *caller*, and if the caller were
        the one holding the build, the cancellation would land on the await
        and skip the assignment that publishes the result. The executor thread
        cannot be cancelled, so it would finish loading the model and throw it
        away — leaving ``_analyzer`` unset, so the next request starts another
        build, while the abandoned one still occupies one of two worker
        threads. A handful of timeouts could then queue real checks behind
        builds nobody is waiting for.

        With the build owned here, a cancelled caller abandons only its own
        wait. The load completes, publishes, and the next caller finds it done.
        """
        if self._analyzer is not None:
            return self._analyzer, self._anonymizer

        async with self._init_lock:
            if self._analyzer is None and self._init_task is None:
                self._init_task = asyncio.ensure_future(self._build_engines())
                # Retrieves the exception of a build nobody is left waiting on,
                # which asyncio would otherwise report as never retrieved.
                self._init_task.add_done_callback(_swallow_result)
            task = self._init_task

        if task is not None:
            try:
                await asyncio.shield(task)
            except BaseException:
                # Distinguish "the build failed" from "our wait was cancelled".
                # A cancelled wait leaves the build running, and the next caller
                # joins it rather than starting a second one. A build that ended
                # badly has to be forgotten, or it is replayed as a stale error
                # on every later call and the adapter never recovers.
                #
                # Cleared here rather than from the done callback because that
                # runs via call_soon: a retry issued immediately after the
                # failure would still see the dead task.
                if task.done() and (task.cancelled() or task.exception()):
                    async with self._init_lock:
                        if self._init_task is task:
                            self._init_task = None
                raise

        return self._analyzer, self._anonymizer

    async def _build_engines(self) -> None:
        """Construct the engines and publish them.

        Publishing happens here, inside the task, rather than in whichever
        caller happened to be waiting — see ``_engines``.
        """

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

    def stream_capability_for(self, options: Dict[str, Any]) -> StreamCapability:
        """Whether this policy's selection is safe to release incrementally.

        The class declares INCREMENTAL because Presidio's findings are spans:
        a card number is a property of twenty-four characters, not of the
        paragraph around them, so a scan of a prefix says something true and
        permanent about that prefix. What the class cannot know is *which*
        entities a policy asked for, and the span argument does not survive
        every answer.

        Two selections take it away:

        An entity with no length bound (see ``UNBOUNDED_LENGTH``) defeats the
        margin. Incremental release holds back enough characters that an
        entity starting before the cut must end inside the scanned text; a URL
        can be longer than any margin worth the latency, so it could be half
        released before it was ever visible to a scan.

        A ``hash`` operator rewrites an entity to 64 hex characters, which is
        longer than most of what it replaces. Redaction that *expands* pushes
        the vetted text past the plaintext offsets the cut was computed from,
        and while the divergence check downstream would catch the result, the
        honest answer is that the bound stops holding.
        """
        entities = self._resolve_entities(options)
        if entities is None:
            # The policy selected nothing, so nothing is detected and nothing
            # is rewritten. Vacuously safe.
            return StreamCapability.INCREMENTAL

        if not set(entities) <= INCREMENTAL_SAFE:
            return StreamCapability.BUFFERED

        configured = options.get('operators') or {}
        for spec in configured.values():
            if isinstance(spec, dict) and spec.get('type') == 'hash':
                return StreamCapability.BUFFERED

        return StreamCapability.INCREMENTAL

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
