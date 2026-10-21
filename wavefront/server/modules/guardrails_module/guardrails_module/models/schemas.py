"""Request and response shapes for the guardrail policy API."""

import re
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class EnforcementMode(str, Enum):
    MONITOR = 'MONITOR'
    ENFORCE = 'ENFORCE'


class WorkflowStage(str, Enum):
    BEFORE_MODEL = 'BEFORE_MODEL'
    AFTER_MODEL = 'AFTER_MODEL'


class FailureMode(str, Enum):
    FAIL_OPEN = 'FAIL_OPEN'
    FAIL_CLOSED = 'FAIL_CLOSED'


class StreamPreference(str, Enum):
    """Whether a streamed response may be released before it is complete."""

    BUFFERED = 'BUFFERED'
    INCREMENTAL = 'INCREMENTAL'


#: Adapters this deployment knows how to construct. Validated here rather than
#: at request time so a typo is a 400 on the settings page instead of a policy
#: that silently checks nothing - an unregistered adapter is indistinguishable
#: from "no checks configured" once the engine is running.
SUPPORTED_ADAPTERS = ('presidio_pii', 'azure_content_safety')


#: The adapter whose options this module validates in detail.
PII_ADAPTER = 'presidio_pii'

#: Presidio entity identifiers are uppercase snake case, e.g. ``IN_AADHAAR``.
#: Matching is case-sensitive inside Presidio, so a lowercase name would select
#: no recogniser and fail the request rather than detecting nothing quietly.
_ENTITY_PATTERN = re.compile(r'^[A-Z][A-Z0-9_]{1,63}$')


class RedactionStylePayload(BaseModel):
    """How one entity type is rewritten once detected."""

    type: Literal['replace', 'mask', 'hash', 'redact'] = 'replace'
    #: Only meaningful for ``replace``; empty falls back to ``[ENTITY_TYPE]``.
    new_value: Optional[str] = Field(default=None, max_length=64)
    #: Characters preserved at the end of the value for ``mask``.
    keep_last: int = Field(default=4, ge=1, le=8)
    masking_char: str = Field(default='*', min_length=1, max_length=1)


class PresidioOptionsPayload(BaseModel):
    """Tuning for the local PII provider.

    ``extra='forbid'`` so a mistyped key is a 400 on the settings page rather
    than an option that is silently stored and never read.
    """

    model_config = {'extra': 'forbid'}

    #: ``None`` means "not configured", which the adapter reads as its default
    #: high-precision set. This is not the same as an empty list, and the two
    #: must stay distinguishable for existing policies to keep behaving the
    #: same - see the validator below.
    entities: Optional[List[str]] = Field(default=None, max_length=120)
    operators: Dict[str, RedactionStylePayload] = Field(default_factory=dict)
    allow_list: List[str] = Field(default_factory=list, max_length=200)
    allow_list_match: Literal['exact', 'regex'] = 'exact'
    language: str = Field(default='en', max_length=8)
    #: Supported by the adapter but not yet exposed in the console.
    score_threshold: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator('entities')
    @classmethod
    def _valid_entity_names(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        if not value:
            raise ValueError(
                'Select at least one entity type, or turn the PII provider '
                'off. A provider that is enabled but checks nothing reads as '
                'protection that is not there.'
            )
        cleaned = []
        for entity in value:
            name = str(entity).strip().upper()
            if not _ENTITY_PATTERN.match(name):
                raise ValueError(f'Not a valid entity type: {entity!r}')
            if name not in cleaned:
                cleaned.append(name)
        return cleaned

    @field_validator('allow_list')
    @classmethod
    def _non_empty_terms(cls, value: List[str]) -> List[str]:
        return [term for term in (str(v).strip() for v in value) if term]

    @model_validator(mode='after')
    def _check_cross_field(self) -> 'PresidioOptionsPayload':
        # Presidio joins allow-list terms into one alternation and compiles it
        # at request time, so a term that cannot compile is an exception inside
        # the adapter - which is an outage, not a warning.
        if self.allow_list_match == 'regex':
            for term in self.allow_list:
                if len(term) > 256:
                    raise ValueError(
                        f'Allow-list pattern is too long ({len(term)} chars, '
                        'maximum 256)'
                    )
                try:
                    re.compile(term)
                except re.error as exc:
                    raise ValueError(
                        f'Allow-list pattern {term!r} is not valid: {exc}'
                    ) from exc

        # An operator for an entity that is never detected is dead config, and
        # usually means a typo in the entity name.
        if self.entities is not None:
            unknown = sorted(set(self.operators) - set(self.entities))
            if unknown:
                raise ValueError(
                    'Redaction style set for entity types that are not '
                    f'selected: {", ".join(unknown)}'
                )
        return self


class AdapterConfigPayload(BaseModel):
    name: str = Field(description='Adapter identifier')
    stages: List[WorkflowStage] = Field(
        default_factory=lambda: [WorkflowStage.BEFORE_MODEL],
        description='Points in the agent loop at which this adapter runs',
    )
    on_error: FailureMode = Field(
        default=FailureMode.FAIL_OPEN,
        description=(
            'Behaviour when the provider is unreachable, throttled or times '
            'out. Does not apply to oversized or wrongly-typed input, which '
            'always fails closed because the caller controls it.'
        ),
    )
    timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    options: Dict[str, Any] = Field(
        default_factory=dict,
        description='Adapter tuning, e.g. severity_threshold or entities',
    )

    @field_validator('name')
    @classmethod
    def _known_adapter(cls, value: str) -> str:
        if value not in SUPPORTED_ADAPTERS:
            raise ValueError(
                f"Unknown adapter '{value}'. Supported: "
                f'{", ".join(SUPPORTED_ADAPTERS)}'
            )
        return value

    @field_validator('stages')
    @classmethod
    def _at_least_one_stage(cls, value: List[WorkflowStage]) -> List[WorkflowStage]:
        if not value:
            raise ValueError('At least one stage is required')
        return value

    @model_validator(mode='after')
    def _validate_known_options(self) -> 'AdapterConfigPayload':
        """Type-check options for adapters we understand, pass the rest through.

        Only the PII adapter has a schema here. Azure's options stay free-form
        so adding a provider does not require schema surgery, and so a newer
        client can send an option this server has not learned about yet.

        The normalised dump is written back, which is what makes entity names
        case-insensitive on input while stored policy stays canonical.
        """
        if self.name != PII_ADAPTER:
            return self

        parsed = PresidioOptionsPayload.model_validate(self.options or {})
        # exclude_defaults, not exclude_none: only keys the admin actually set
        # are stored. An untouched card round-trips as `{}` rather than growing
        # a full set of defaults, which keeps the "absent means adapter
        # defaults" contract intact for every policy saved before this existed.
        self.options = parsed.model_dump(exclude_defaults=True)
        return self


class UpdateGuardrailPolicyPayload(BaseModel):
    is_enabled: bool = Field(
        description='Master switch. When false no safety provider is called.'
    )
    mode: EnforcementMode = Field(
        default=EnforcementMode.MONITOR,
        description=(
            'MONITOR records verdicts without acting on them; ENFORCE blocks '
            'and redacts.'
        ),
    )
    adapters: List[AdapterConfigPayload] = Field(default_factory=list)
    stream: StreamPreference = Field(
        default=StreamPreference.BUFFERED,
        description=(
            'BUFFERED withholds a streamed response until the whole of it has '
            'been checked. INCREMENTAL releases it as it arrives, keeping back '
            'enough of the tail that a finding cannot straddle the boundary. '
            'Only takes effect where every configured adapter supports it; '
            'the response reports the mode actually in force.'
        ),
    )

    @field_validator('adapters')
    @classmethod
    def _no_duplicates(
        cls, value: List[AdapterConfigPayload]
    ) -> List[AdapterConfigPayload]:
        names = [adapter.name for adapter in value]
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            raise ValueError(
                f'Adapter configured more than once: {", ".join(sorted(duplicates))}'
            )
        return value


class PiiPreviewPayload(BaseModel):
    """Run a draft PII policy against sample text without saving it.

    The length cap is a real control, not a formality: this is the one endpoint
    where admin-supplied configuration meets admin-supplied text, and every
    selected entity's patterns run over the whole string.
    """

    text: str = Field(min_length=1, max_length=4000)
    options: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('options')
    @classmethod
    def _validated_options(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        # Same schema as a save, so the preview cannot show behaviour the
        # policy editor would then refuse to store.
        return PresidioOptionsPayload.model_validate(value or {}).model_dump(
            exclude_defaults=True
        )


class GuardrailPolicyResponse(BaseModel):
    namespace: str
    is_enabled: bool
    mode: EnforcementMode
    adapters: List[AdapterConfigPayload]
    stream: StreamPreference = StreamPreference.BUFFERED
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PolicyPreviewPayload(UpdateGuardrailPolicyPayload):
    """Run a whole draft policy against sample text, across every provider.

    Extends the save payload rather than redeclaring the fields, so a preview
    is impossible to express in a shape the editor could not also save. If a
    draft passes preview it will pass ``PUT``.

    Separate from :class:`PiiPreviewPayload`, which answers a narrower question:
    that one tunes the entity picker and reports match offsets and scores, this
    one reports the verdict the engine would reach once every adapter has run
    and their actions have been composed.
    """

    text: str = Field(
        min_length=1,
        max_length=4000,
        description='Sample text to evaluate at both stages.',
    )
