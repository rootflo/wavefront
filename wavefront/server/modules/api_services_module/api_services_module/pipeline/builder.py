"""Pipeline builder for creating service pipelines."""

from typing import List
from ..models.pipeline import CompositePipelineStage, PipelineStage
from ..models.service import ServiceDefinition, ApiConfig
from ..auth.handlers import AuthHandlerFactory
from .stages import (
    RequestHeadersForwarderStage,
    HeaderInjectorStage,
    ApiProcessorStage,
    PayloadValidatorStage,
    RequestSenderStage,
    ResponseMapperStage,
)


class PipelineBuilder:
    """Builder for creating service pipelines using the composite pattern."""

    @staticmethod
    def build_auth_pipeline(
        service_definition: ServiceDefinition,
    ) -> CompositePipelineStage:
        """
        Build authentication pipeline for a service.

        Pipeline: [Authenticator → Header Injector]
        """
        stages: List[PipelineStage] = []

        # 1. Authenticator stage
        auth_handler = AuthHandlerFactory.create_handler(service_definition.auth)
        stages.append(auth_handler)

        # 2. Auth header injector (for additional auth headers)
        if service_definition.auth.additional_headers:
            auth_header_injector = HeaderInjectorStage(
                service_definition.auth.additional_headers, 'auth_header_injector'
            )
            stages.append(auth_header_injector)

        return CompositePipelineStage(
            name=f'auth_pipeline_{service_definition.id}', stages=stages
        )

    @staticmethod
    def build_api_pipeline(
        service_definition: ServiceDefinition, api_config: ApiConfig
    ) -> CompositePipelineStage:
        """
        Build API processing pipeline for a specific API.

        Pipeline: [API Processor → Header Injector → Payload Validator → Request Sender → Response Mapper]
        Note: Skipping preprocessor and postprocessor as requested
        """
        stages: List[PipelineStage] = []

        # 1. API processor stage
        api_processor = ApiProcessorStage(api_config, service_definition)
        stages.append(api_processor)

        # 2. API header injector (for additional API headers)
        if api_config.additional_headers:
            api_header_injector = HeaderInjectorStage(
                api_config.additional_headers, f'api_header_injector_{api_config.id}'
            )
            stages.append(api_header_injector)

        # 3. Payload validator stage (validates request body before sending)
        payload_validator = PayloadValidatorStage(api_config)
        stages.append(payload_validator)

        # 4. Request sender stage
        request_sender = RequestSenderStage()
        stages.append(request_sender)

        # 5. Response mapper stage
        response_mapper = ResponseMapperStage(api_config)
        stages.append(response_mapper)

        return CompositePipelineStage(
            name=f'api_pipeline_{service_definition.id}_{api_config.id}', stages=stages
        )

    @staticmethod
    def build_service_pipeline(
        service_definition: ServiceDefinition, api_config: ApiConfig
    ) -> CompositePipelineStage:
        """
        Build complete service pipeline.

        Pipeline: [Request Headers Forwarder → Auth Pipeline → API Pipeline]
        """
        stages: List[PipelineStage] = []

        # 0. Request headers forwarder (forward incoming headers to backend)
        headers_forwarder = RequestHeadersForwarderStage()
        stages.append(headers_forwarder)

        # 1. Authentication pipeline
        auth_pipeline = PipelineBuilder.build_auth_pipeline(service_definition)
        stages.append(auth_pipeline)

        # 2. API processing pipeline
        api_pipeline = PipelineBuilder.build_api_pipeline(
            service_definition, api_config
        )
        stages.append(api_pipeline)

        return CompositePipelineStage(
            name=f'service_pipeline_{service_definition.id}_{api_config.id}',
            stages=stages,
        )


class PipelineCache:
    """Cache for compiled pipelines to improve performance."""

    def __init__(self):
        self._pipeline_cache = {}

    def get_pipeline(
        self, service_id: str, api_id: str, api_version: str = 'v1'
    ) -> CompositePipelineStage:
        """Get cached pipeline or None if not found."""
        cache_key = f'{service_id}:{api_id}:{api_version}'
        return self._pipeline_cache.get(cache_key)

    def cache_pipeline(
        self,
        service_id: str,
        api_id: str,
        pipeline: CompositePipelineStage,
        api_version: str = 'v1',
    ):
        """Cache a compiled pipeline."""
        cache_key = f'{service_id}:{api_id}:{api_version}'
        self._pipeline_cache[cache_key] = pipeline

    def invalidate_service(self, service_id: str):
        """Invalidate all pipelines for a service."""
        keys_to_remove = [
            key
            for key in self._pipeline_cache.keys()
            if key.startswith(f'{service_id}:')
        ]
        for key in keys_to_remove:
            del self._pipeline_cache[key]

    def clear_all(self):
        """Clear all cached pipelines."""
        self._pipeline_cache.clear()

    def get_stats(self) -> dict:
        """Get cache statistics."""
        return {
            'cached_pipelines': len(self._pipeline_cache),
            'cache_keys': list(self._pipeline_cache.keys()),
        }
