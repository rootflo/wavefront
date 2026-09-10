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

#: High-precision identifiers only.
#:
#: Presidio's full recogniser set includes PERSON, LOCATION, DATE_TIME, NRP
#: and URL, which fire constantly on ordinary business prompts — "What's the
#: weather in London on Monday?" comes back as "...in <LOCATION> on
#: <DATE_TIME>". Those are opt-in via policy rather than on by default,
#: because a guardrail that mangles normal traffic gets switched off.
DEFAULT_ENTITIES: Sequence[str] = (
    'CREDIT_CARD',
    'CRYPTO',
    'EMAIL_ADDRESS',
    'IBAN_CODE',
    'IP_ADDRESS',
    'MEDICAL_LICENSE',
    'PHONE_NUMBER',
    'US_BANK_NUMBER',
    'US_DRIVER_LICENSE',
    'US_PASSPORT',
    'US_SSN',
)

#: Defer to each recogniser's own confidence rather than imposing a floor.
#:
#: Presidio calibrates per recogniser and then boosts on surrounding context,
#: and the identifiers here land well below a naive cutoff: a dashed US SSN,
#: a phone number, and a card number whose Luhn checksum does not validate all
#: score under 0.5. An earlier 0.5 default therefore reported "clean" for
#: every one of them while appearing to work, because EMAIL_ADDRESS scores 1.0
#: and was the only thing that ever fired.
#:
#: The trade-off is accepted deliberately: this list is identifiers only, so a
#: false positive redacts something like a nine-digit order number, whereas a
#: false negative ships an SSN to a third-party model. Policy can raise the
#: floor per namespace via the ``score_threshold`` option.
DEFAULT_SCORE_THRESHOLD = 0.0

_IMPORT_HINT = (
    'Presidio is not installed. Install the guardrails extra:\n'
    "    pip install 'flo_ai[guardrails]'\n"
    'and download a spaCy model:\n'
    '    python -m spacy download en_core_web_lg'
)


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
    ) -> None:
        self._entities = list(entities) if entities else list(DEFAULT_ENTITIES)
        self._score_threshold = score_threshold
        self._language = language
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
                return AnalyzerEngine(), AnonymizerEngine()

            loop = asyncio.get_running_loop()
            analyzer, anonymizer = await loop.run_in_executor(self._executor, _build)
            self._analyzer, self._anonymizer = analyzer, anonymizer
            logger.debug('Presidio engines initialised')

        return self._analyzer, self._anonymizer

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

        entities = list(request.options.get('entities') or self._entities)
        threshold = float(request.options.get('score_threshold', self._score_threshold))
        language = request.options.get('language') or self._language

        analyzer, anonymizer = await self._engines()
        loop = asyncio.get_running_loop()

        findings = await loop.run_in_executor(
            self._executor,
            lambda: analyzer.analyze(
                text=text,
                language=language,
                entities=entities or None,
                score_threshold=threshold,
            ),
        )
        if not findings:
            return self._allow()

        anonymized = await loop.run_in_executor(
            self._executor,
            lambda: anonymizer.anonymize(text=text, analyzer_results=findings),
        )

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

    @staticmethod
    def _metadata(findings: List[Any], entity_types: List[str]) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for finding in findings:
            counts[finding.entity_type] = counts.get(finding.entity_type, 0) + 1
        return {'entity_counts': counts, 'entity_types': entity_types}
