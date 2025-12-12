import uuid
import re
from typing import Optional, Dict
import httpx
import json
from fastapi import Request, HTTPException, status
from fastapi.responses import StreamingResponse, Response
from common_module.log.logger import logger
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from llm_inference_config_module.models.schemas import InferenceEngineType
from llm_inference_config_module.services.llm_inference_config_service import (
    LlmInferenceConfigService,
)


class InferenceProxyService:
    def __init__(
        self,
        llm_inference_config_service: LlmInferenceConfigService,
    ):
        self.llm_inference_config_service = llm_inference_config_service

        # Create a single reusable client
        timeout = httpx.Timeout(60.0, connect=30.0)
        limits = httpx.Limits(
            max_keepalive_connections=20, max_connections=100, keepalive_expiry=60
        )
        self._client = httpx.AsyncClient(timeout=timeout, limits=limits)

        # Provider-specific auth header mapping
        self._auth_header_mapping = {
            InferenceEngineType.OPENAI: self._prepare_openai_auth,
            InferenceEngineType.GEMINI: self._prepare_gemini_auth,
            InferenceEngineType.ANTHROPIC: self._prepare_anthropic_auth,
            InferenceEngineType.AZURE_OPENAI: self._prepare_azure_openai_auth,
            InferenceEngineType.OLLAMA: self._prepare_ollama_auth,
            InferenceEngineType.VLLM: self._prepare_vllm_auth,
        }

        # Provider-specific model extraction mapping
        self._model_extraction_mapping = {
            InferenceEngineType.OPENAI: self._extract_openai_model,
            InferenceEngineType.GEMINI: self._extract_gemini_model,
            InferenceEngineType.ANTHROPIC: self._extract_anthropic_model,
            InferenceEngineType.AZURE_OPENAI: self._extract_azure_openai_model,
            InferenceEngineType.OLLAMA: self._extract_ollama_model,
            InferenceEngineType.VLLM: self._extract_vllm_model,
        }

        # Provider-specific streaming detection mapping
        self._streaming_detection_mapping = {
            InferenceEngineType.OPENAI: self._detect_openai_streaming,
            InferenceEngineType.GEMINI: self._detect_gemini_streaming,
            InferenceEngineType.ANTHROPIC: self._detect_anthropic_streaming,
            InferenceEngineType.AZURE_OPENAI: self._detect_azure_openai_streaming,
            InferenceEngineType.OLLAMA: self._detect_ollama_streaming,
            InferenceEngineType.VLLM: self._detect_vllm_streaming,
        }

    async def close(self):
        """Close the HTTP client - call this on app shutdown"""
        await self._client.aclose()

    async def get_model_config(self, model_id: str) -> Optional[LlmInferenceConfig]:
        """Get model configuration by ID."""

        try:
            model_uuid = uuid.UUID(model_id)
        except ValueError:
            return None
        model_config = await self.llm_inference_config_service.get_config(model_uuid)
        if not model_config:
            return None

        if isinstance(model_config, LlmInferenceConfig):
            return model_config

        return LlmInferenceConfig(**model_config)

    def construct_target_url(self, base_url: str, model_call_path: str) -> str:
        """Construct the target URL by combining base_url and model_call_path."""
        # Remove trailing slash from base_url and leading slash from model_call_path
        base_url = base_url.rstrip('/')
        model_call_path = model_call_path.lstrip('/')

        return f'{base_url}/{model_call_path}'

    def detect_streaming(
        self,
        provider_type: InferenceEngineType,
        parsed_data: dict,
        model_call_path: str,
    ) -> bool:
        """Detect if this is a streaming request using provider-specific logic."""
        streaming_detector = self._streaming_detection_mapping.get(provider_type)

        if not streaming_detector:
            logger.warning(f'No streaming detector found for provider: {provider_type}')
            # Fallback to OpenAI-style detection for unknown providers
            return isinstance(parsed_data, dict) and parsed_data.get('stream', False)

        return streaming_detector(parsed_data, model_call_path)

    def _prepare_openai_auth(self, headers: Dict[str, str], api_key: str) -> None:
        """Prepare OpenAI authentication headers."""
        headers['authorization'] = f'Bearer {api_key}'

    def _prepare_gemini_auth(self, headers: Dict[str, str], api_key: str) -> None:
        """Prepare Gemini authentication headers."""
        headers['x-goog-api-key'] = api_key
        del headers['authorization']

    def _prepare_anthropic_auth(self, headers: Dict[str, str], api_key: str) -> None:
        """Prepare Anthropic authentication headers."""
        headers['x-api-key'] = api_key

    def _prepare_azure_openai_auth(self, headers: Dict[str, str], api_key: str) -> None:
        """Prepare Azure OpenAI authentication headers."""
        headers['api-key'] = api_key

    def _prepare_ollama_auth(self, headers: Dict[str, str], api_key: str) -> None:
        """Prepare Ollama authentication headers (typically no auth required)."""
        # Ollama typically runs locally without authentication
        # If auth is needed, it can be added here
        pass

    def _prepare_vllm_auth(self, headers: Dict[str, str], api_key: str) -> None:
        """Prepare vLLM authentication headers."""
        # vLLM auth depends on deployment configuration
        # Default to Bearer token format
        if api_key:
            headers['authorization'] = f'Bearer {api_key}'

    def _extract_openai_model(
        self, parsed_data: dict, model_call_path: str
    ) -> Optional[str]:
        """Extract model from OpenAI-style request body."""
        return parsed_data.get('model')

    def _extract_gemini_model(
        self, parsed_data: dict, model_call_path: str
    ) -> Optional[str]:
        """Extract model from Gemini URL path. Expected format: v1beta/models/{model}:generateContent"""
        # Pattern: models/{model}:generateContent or models/{model}:streamGenerateContent
        pattern = r'/models/([^/:]+):'
        match = re.search(pattern, model_call_path)
        return match.group(1) if match else None

    def _extract_anthropic_model(
        self, parsed_data: dict, model_call_path: str
    ) -> Optional[str]:
        """Extract model from Anthropic-style request body."""
        return parsed_data.get('model')

    def _extract_azure_openai_model(
        self, parsed_data: dict, model_call_path: str
    ) -> Optional[str]:
        """Extract model from Azure OpenAI URL path. Expected format: deployments/{model}/chat/completions"""
        pattern = r'/deployments/([^/]+)/'
        match = re.search(pattern, model_call_path)
        return match.group(1) if match else None

    def _extract_ollama_model(
        self, parsed_data: dict, model_call_path: str
    ) -> Optional[str]:
        """Extract model from Ollama request - typically in body like OpenAI."""
        return parsed_data.get('model')

    def _extract_vllm_model(
        self, parsed_data: dict, model_call_path: str
    ) -> Optional[str]:
        """Extract model from vLLM request - typically in body like OpenAI."""
        return parsed_data.get('model')

    def _detect_openai_streaming(self, parsed_data: dict, model_call_path: str) -> bool:
        """Detect OpenAI streaming from request body."""
        return isinstance(parsed_data, dict) and parsed_data.get('stream', False)

    def _detect_gemini_streaming(self, parsed_data: dict, model_call_path: str) -> bool:
        """Detect Gemini streaming from URL path (streamGenerateContent vs generateContent)."""
        return 'streamGenerateContent' in model_call_path

    def _detect_anthropic_streaming(
        self, parsed_data: dict, model_call_path: str
    ) -> bool:
        """Detect Anthropic streaming from request body."""
        return isinstance(parsed_data, dict) and parsed_data.get('stream', False)

    def _detect_azure_openai_streaming(
        self, parsed_data: dict, model_call_path: str
    ) -> bool:
        """Detect Azure OpenAI streaming from request body."""
        return isinstance(parsed_data, dict) and parsed_data.get('stream', False)

    def _detect_ollama_streaming(self, parsed_data: dict, model_call_path: str) -> bool:
        """Detect Ollama streaming from request body."""
        return isinstance(parsed_data, dict) and parsed_data.get('stream', False)

    def _detect_vllm_streaming(self, parsed_data: dict, model_call_path: str) -> bool:
        """Detect vLLM streaming from request body."""
        return isinstance(parsed_data, dict) and parsed_data.get('stream', False)

    def prepare_headers(
        self, request: Request, model_config: LlmInferenceConfig
    ) -> Dict[str, str]:
        """Prepare headers for the forwarded request with provider-specific auth."""
        headers = {}

        # Copy most headers from the original request
        excluded_headers = {
            'host',
            'content-length',
            'transfer-encoding',
            'connection',
            'upgrade',
            'proxy-authenticate',
            'proxy-authorization',
        }

        for key, value in request.headers.items():
            if key.lower() not in excluded_headers:
                headers[key] = value

        # Add provider-specific authentication if api_key is provided
        if model_config.api_key:
            provider_type = InferenceEngineType(model_config.type)
            auth_method = self._auth_header_mapping.get(provider_type)

            if auth_method:
                auth_method(headers, model_config.api_key)
            else:
                logger.warning(f'No auth method found for provider: {provider_type}')

        return headers

    async def forward_request(
        self,
        target_url: str,
        headers: Dict[str, str],
        body: bytes,
        query_params: Dict[str, str],
        is_streaming: bool = False,
    ) -> Response:
        """Forward the request to the target URL."""
        try:
            if is_streaming:
                # Build the request
                req = self._client.build_request(
                    method='POST',
                    url=target_url,
                    headers=headers,
                    content=body,
                    params=query_params,
                )

                # Send with stream=True but don't close the response
                response = await self._client.send(req, stream=True)

                async def generate():
                    try:
                        async for chunk in response.aiter_bytes():
                            yield chunk
                    finally:
                        # Ensure response is closed after streaming completes
                        await response.aclose()

                return StreamingResponse(
                    generate(),
                    status_code=response.status_code,
                    headers={
                        k: v
                        for k, v in response.headers.items()
                        if k.lower()
                        not in ['content-length', 'transfer-encoding', 'connection']
                    },
                    media_type=response.headers.get('content-type', 'application/json'),
                )
            else:
                response = await self._client.post(
                    url=target_url,
                    headers=headers,
                    content=body,
                    params=query_params,
                )
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers={
                        k: v
                        for k, v in response.headers.items()
                        if k.lower()
                        not in [
                            'content-length',
                            'transfer-encoding',
                            'connection',
                            'content-encoding',
                        ]
                    },
                )
        except httpx.TimeoutException as e:
            logger.error(f'Timeout when forwarding to {target_url}: {str(e)}')
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail='Request to target model API timed out',
            )
        except httpx.RequestError as e:
            logger.error(f'Request error when forwarding to {target_url}: {str(e)}')
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail='Error communicating with target model API',
            )

    async def proxy_inference_request(
        self, model_id: str, model_call_path: str, request: Request
    ) -> Response:
        """Main method to proxy an inference request."""
        logger.info(
            f'Proxying inference request: model_id={model_id}, path={model_call_path}'
        )

        model_config = await self.get_model_config(model_id)
        if not model_config:
            logger.warning(f'Model not found: {model_id}')
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f'Model configuration not found for model ID: {model_id}',
            )

        if not model_config.base_url:
            logger.error(f'Base URL not configured for model: {model_id}')
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f'Base URL not configured for model ID: {model_id}',
            )

        target_url = self.construct_target_url(model_config.base_url, model_call_path)

        # Read body once and parse JSON once
        body = await request.body()

        try:
            parsed_data = json.loads(body) if body else {}
        except json.JSONDecodeError as e:
            logger.error(f'Invalid JSON in request body: {str(e)}')
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'Invalid JSON in request body: {str(e)}',
            )

        # Validate model compatibility using provider-specific extraction
        provider_type = InferenceEngineType(model_config.type)
        model_extractor = self._model_extraction_mapping.get(provider_type)

        if not model_extractor:
            logger.warning(f'No model extractor found for provider: {provider_type}')
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f'Unsupported provider type: {provider_type}',
            )

        request_model = model_extractor(parsed_data, model_call_path)

        if not request_model:
            detail_msg = (
                'Missing "model" field in request body'
                if provider_type
                in [InferenceEngineType.OPENAI, InferenceEngineType.ANTHROPIC]
                else f'Could not extract model from URL path: {model_call_path}'
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=detail_msg,
            )

        if request_model != model_config.llm_model:
            logger.warning(
                f'Model mismatch for {provider_type}: requested={request_model}, configured={model_config.llm_model}'
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'Model mismatch: requested "{request_model}" but proxy is configured for "{model_config.llm_model}"',
            )

        headers = self.prepare_headers(request, model_config)
        query_params = dict(request.query_params)

        # Check streaming using provider-specific detection
        is_streaming = self.detect_streaming(
            provider_type, parsed_data, model_call_path
        )

        response = await self.forward_request(
            target_url=target_url,
            headers=headers,
            body=body,  # Pass original body bytes for forwarding
            query_params=query_params,
            is_streaming=is_streaming,
        )

        logger.info(f'Proxied to {target_url}, status: {response.status_code}')
        return response
