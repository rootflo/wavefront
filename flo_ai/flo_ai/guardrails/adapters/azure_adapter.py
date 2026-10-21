"""Azure AI Content Safety: text moderation and Prompt Shields."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import httpx

from flo_ai.utils.logger import logger

from ..contracts import (
    AssessmentRequest,
    AssessmentStatus,
    CheckResult,
    FailureClass,
    PolicyAction,
    StreamCapability,
    WorkflowStage,
)
from .base_adapter import BaseAdapter

#: Azure's documented per-request text limit for the analyze endpoint.
MAX_CHARS_PER_REQUEST = 10_000

#: Refuse rather than fan out unboundedly on a huge payload. Ten requests is
#: already an expensive check; beyond that the caller gets an explicit
#: rejection (which fails closed) instead of a surprise bill.
MAX_CHUNKS = 10

#: Azure severity is 0 (safe), 2 (low), 4 (medium), 6 (high) in the default
#: FourSeverityLevels mode. Blocking at 2 — as the first implementation did
#: with ``severity > 0`` — rejects a large share of ordinary traffic, so the
#: default sits at medium and is tunable per category from policy.
DEFAULT_SEVERITY_THRESHOLD = 4
MAX_SEVERITY = 6

CATEGORIES = ('Hate', 'SelfHarm', 'Sexual', 'Violence')

PROMPT_SHIELDS_API_VERSION = '2024-09-01'

_IMPORT_HINT = (
    'azure-ai-contentsafety is not installed. Install the guardrails extra:\n'
    "    pip install 'flo_ai[guardrails]'"
)


class AzureContentSafetyAdapter(BaseAdapter):
    """Moderation plus prompt-injection detection.

    Two transports, deliberately. Category moderation goes through the
    ``azure-ai-contentsafety`` SDK, which models it properly. Prompt Shields
    has no typed method in any released version of that SDK, so it is called
    over REST; writing it by hand is preferable to depending on a preview
    package for the one check that detects injection attacks.
    """

    #: Inherited from BaseAdapter, but stated rather than left implicit,
    #: because it is a decision and not an omission: a guarded stream never
    #: releases text early while this adapter is configured.
    #:
    #: The verdict is a property of the whole passage. ``_moderate`` takes the
    #: worst severity across its chunks precisely because severity is not
    #: additive over a prefix -- half a sentence can read as benign and the
    #: sentence as hateful, and the score for the first is not a partial
    #: answer to the second. Scanning prefixes would also bill a network call
    #: per scan rather than one per response.
    stream_capability = StreamCapability.BUFFERED

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        severity_threshold: int = DEFAULT_SEVERITY_THRESHOLD,
        category_thresholds: Optional[Dict[str, int]] = None,
        enable_prompt_shields: bool = True,
        enable_moderation: bool = True,
        request_timeout: float = 4.0,
    ) -> None:
        self._endpoint = endpoint.rstrip('/')
        self._api_key = api_key
        self._severity_threshold = severity_threshold
        self._category_thresholds = dict(category_thresholds or {})
        self._enable_prompt_shields = enable_prompt_shields
        self._enable_moderation = enable_moderation
        self._request_timeout = request_timeout
        self._client: Any = None
        self._http: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return 'azure_content_safety'

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _safety_client(self) -> Any:
        """Lazily build the SDK client, once, under a lock.

        Without the lock, concurrent first calls each build a client and all
        but one leak its connection pool.
        """
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                try:
                    from azure.ai.contentsafety.aio import ContentSafetyClient
                    from azure.core.credentials import AzureKeyCredential
                except ImportError as exc:  # pragma: no cover - env dependent
                    raise RuntimeError(_IMPORT_HINT) from exc
                self._client = ContentSafetyClient(
                    self._endpoint, AzureKeyCredential(self._api_key)
                )
        return self._client

    async def _http_client(self) -> httpx.AsyncClient:
        if self._http is None:
            async with self._client_lock:
                if self._http is None:
                    self._http = httpx.AsyncClient(
                        base_url=self._endpoint,
                        timeout=self._request_timeout,
                        headers={
                            'Ocp-Apim-Subscription-Key': self._api_key,
                            'Content-Type': 'application/json',
                        },
                    )
        return self._http

    # -- evaluation ------------------------------------------------------

    async def evaluate(self, request: AssessmentRequest) -> CheckResult:
        if not isinstance(request.content, str):
            return self._error(
                FailureClass.INPUT_REJECTED,
                'Azure Content Safety only evaluates text content',
                finding_code='guardrail.unsupported_content',
            )

        text = request.content
        if not text.strip():
            return self._allow()

        chunks = self._chunk(text)
        if chunks is None:
            # Caller-controlled size, so this must fail closed rather than
            # wave through anything long enough to exceed the limit.
            return self._error(
                FailureClass.INPUT_REJECTED,
                f'Content exceeds {MAX_CHARS_PER_REQUEST * MAX_CHUNKS} characters',
                finding_code='guardrail.content_too_large',
            )

        options = request.options
        checks: List[Any] = []

        if options.get('enable_moderation', self._enable_moderation):
            checks.append(self._moderate(chunks, options))
        # Injection detection only makes sense on the way in; model output is
        # not a prompt, and scanning it would bill a request per response.
        shields_on = options.get('enable_prompt_shields', self._enable_prompt_shields)
        if shields_on and request.context.workflow_stage is WorkflowStage.BEFORE_MODEL:
            checks.append(self._shield(chunks))

        if not checks:
            return self._allow()

        results = await asyncio.gather(*checks)
        for result in results:
            if result.action is not PolicyAction.ALLOW:
                return result
        return self._allow()

    @staticmethod
    def _chunk(text: str) -> Optional[List[str]]:
        if len(text) <= MAX_CHARS_PER_REQUEST:
            return [text]
        if len(text) > MAX_CHARS_PER_REQUEST * MAX_CHUNKS:
            return None
        return [
            text[i : i + MAX_CHARS_PER_REQUEST]
            for i in range(0, len(text), MAX_CHARS_PER_REQUEST)
        ]

    # -- category moderation ---------------------------------------------

    async def _moderate(
        self, chunks: List[str], options: Dict[str, Any]
    ) -> CheckResult:
        client = await self._safety_client()
        thresholds = self._thresholds(options)

        worst: Dict[str, int] = {}
        for chunk in chunks:
            try:
                # analyze_text accepts raw JSON as well as AnalyzeTextOptions,
                # so the request model is not imported here. That keeps the
                # only hard dependency on the SDK in client construction,
                # which a test can substitute.
                response = await client.analyze_text({'text': chunk})
            except Exception as exc:
                return self._from_exception(exc, 'moderation')
            for analysis in getattr(response, 'categories_analysis', None) or []:
                category = self._category_name(analysis)
                severity = int(getattr(analysis, 'severity', 0) or 0)
                worst[category] = max(worst.get(category, 0), severity)

        violations = [
            (category, severity)
            for category, severity in worst.items()
            if severity >= thresholds.get(category, self._severity_threshold)
        ]
        if not violations:
            return self._allow(
                severity=self._normalise(max(worst.values(), default=0)),
            )

        violations.sort(key=lambda item: item[1], reverse=True)
        summary = ', '.join(f'{c} ({s})' for c, s in violations)
        return CheckResult(
            status=AssessmentStatus.VIOLATION,
            action=PolicyAction.BLOCK,
            adapter=self.name,
            finding_code='safety.category_violation',
            message=f'Blocked by content safety: {summary}',
            severity=self._normalise(violations[0][1]),
            # Category severities only - never the analysed text.
            provider_metadata={'severities': worst},
        )

    def _thresholds(self, options: Dict[str, Any]) -> Dict[str, int]:
        merged = dict(self._category_thresholds)
        merged.update(options.get('category_thresholds') or {})
        default = int(options.get('severity_threshold', self._severity_threshold))
        return {category: merged.get(category, default) for category in CATEGORIES}

    @staticmethod
    def _category_name(analysis: Any) -> str:
        category = getattr(analysis, 'category', '')
        return str(getattr(category, 'value', category))

    @staticmethod
    def _normalise(severity: int) -> float:
        return round(min(severity, MAX_SEVERITY) / MAX_SEVERITY, 3)

    # -- prompt shields --------------------------------------------------

    async def _shield(self, chunks: List[str]) -> CheckResult:
        """Detect prompt-injection / jailbreak attempts.

        Called over REST because the released Python SDK exposes no
        ``shield_prompt`` method - the GA client offers only ``analyze_text``
        and ``analyze_image``.
        """
        client = await self._http_client()
        for chunk in chunks:
            try:
                response = await client.post(
                    '/contentsafety/text:shieldPrompt',
                    params={'api-version': PROMPT_SHIELDS_API_VERSION},
                    json={'userPrompt': chunk, 'documents': []},
                )
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:
                return self._from_exception(exc, 'prompt shields')

            analysis = payload.get('userPromptAnalysis') or {}
            if analysis.get('attackDetected'):
                return CheckResult(
                    status=AssessmentStatus.VIOLATION,
                    action=PolicyAction.BLOCK,
                    adapter=self.name,
                    finding_code='safety.prompt_injection',
                    message='Blocked by Prompt Shields: prompt attack detected',
                    severity=1.0,
                )
        return self._allow()

    # -- errors ----------------------------------------------------------

    def _from_exception(self, exc: Exception, operation: str) -> CheckResult:
        """Map a provider failure onto a failure class.

        Everything here is infrastructure: unreachable, throttled, or a bad
        credential. None of it is caller-controlled, so the policy's fail-open
        setting legitimately applies.
        """
        status = getattr(exc, 'status_code', None)
        if status is None and isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code

        if status == 429:
            message = f'Azure {operation} rate-limited (429)'
        elif status is not None:
            message = f'Azure {operation} failed with HTTP {status}'
        else:
            message = f'Azure {operation} failed: {exc}'

        logger.error(f'Guardrail: {message}')
        return self._error(
            FailureClass.INFRASTRUCTURE,
            message,
            finding_code='guardrail.provider_error',
            provider_metadata={'status_code': status} if status else None,
        )
