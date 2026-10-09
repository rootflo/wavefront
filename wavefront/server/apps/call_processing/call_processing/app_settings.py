"""Call-processing settings from config.ini (no direct env reads in services)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class CallEvalSettings:
    azure_endpoint: str
    azure_api_key: str
    llm_model: str
    api_version: str

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
    enable_tracing: bool
    enable_turn_tracking: bool
    otlp_endpoint: str | None
    tracing_service_name: str
    enable_filler_phrases_before_tool_call: bool


@dataclass(frozen=True)
class CallProcessingAppSettings:
    call_eval: CallEvalSettings
    pipecat: PipecatSettings

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> CallProcessingAppSettings:
        call_eval = config['call_eval']
        pipecat = config['pipecat']

        def truthy(value: Any) -> bool:
            return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}

        otlp = pipecat.get('otlp_endpoint') or None
        if otlp == '':
            otlp = None

        return cls(
            call_eval=CallEvalSettings(
                azure_endpoint=call_eval['azure_endpoint'],
                azure_api_key=call_eval['azure_api_key'],
                llm_model=call_eval['llm_model'],
                api_version=call_eval['api_version'],
            ),
            pipecat=PipecatSettings(
                enable_tracing=truthy(pipecat['enable_tracing']),
                enable_turn_tracking=truthy(pipecat['enable_turn_tracking']),
                otlp_endpoint=otlp,
                tracing_service_name=pipecat['tracing_service_name'],
                enable_filler_phrases_before_tool_call=truthy(
                    pipecat['enable_filler_phrases_before_tool_call']
                ),
            ),
        )
