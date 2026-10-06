"""Call-processing settings from config.ini (no direct env reads in services)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CallEvalSettings:
    azure_endpoint: str = ''
    azure_api_key: str = ''
    llm_model: str = 'gpt-4.1'
    api_version: str = '2025-01-01-preview'

    def as_azure_dict(self) -> dict[str, str] | None:
        endpoint = self.azure_endpoint.rstrip('/')
        if not endpoint or not self.azure_api_key:
            return None
        return {
            'endpoint': endpoint,
            'api_key': self.azure_api_key,
            'llm_model': self.llm_model,
            'api_version': self.api_version,
        }


@dataclass(frozen=True)
class PipecatSettings:
    enable_tracing: bool = True
    enable_turn_tracking: bool = True
    otlp_endpoint: str | None = None
    tracing_service_name: str = 'call-processing'
    enable_filler_phrases_before_tool_call: bool = False


@dataclass(frozen=True)
class CallProcessingAppSettings:
    call_eval: CallEvalSettings
    pipecat: PipecatSettings

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> CallProcessingAppSettings:
        call_eval = config.get('call_eval') or {}
        pipecat = config.get('pipecat') or {}

        def truthy(value: Any, default: bool = True) -> bool:
            if value is None or value == '':
                return default
            return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}

        otlp = pipecat.get('otlp_endpoint') or None
        if otlp == '':
            otlp = None

        return cls(
            call_eval=CallEvalSettings(
                azure_endpoint=call_eval.get('azure_endpoint') or '',
                azure_api_key=call_eval.get('azure_api_key') or '',
                llm_model=call_eval.get('llm_model') or 'gpt-4.1',
                api_version=call_eval.get('api_version') or '2025-01-01-preview',
            ),
            pipecat=PipecatSettings(
                enable_tracing=truthy(pipecat.get('enable_tracing'), True),
                enable_turn_tracking=truthy(pipecat.get('enable_turn_tracking'), True),
                otlp_endpoint=otlp,
                tracing_service_name=pipecat.get('tracing_service_name')
                or 'call-processing',
                enable_filler_phrases_before_tool_call=truthy(
                    pipecat.get('enable_filler_phrases_before_tool_call'), False
                ),
            ),
        )


_settings: CallProcessingAppSettings | None = None


def configure_call_processing(settings: CallProcessingAppSettings) -> None:
    global _settings
    _settings = settings


def get_call_processing_settings() -> CallProcessingAppSettings:
    if _settings is None:
        return CallProcessingAppSettings(
            call_eval=CallEvalSettings(), pipecat=PipecatSettings()
        )
    return _settings
