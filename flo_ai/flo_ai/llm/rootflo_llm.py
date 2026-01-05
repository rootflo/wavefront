from enum import Enum
from typing import AsyncIterator, Dict, Any, List, Optional
from datetime import datetime, timedelta
from flo_ai.models.chat_message import ImageMessageContent
import jwt
import httpx
import asyncio
from .base_llm import BaseLLM
from .openai_llm import OpenAI
from .gemini_llm import Gemini
from .anthropic_llm import Anthropic
from .openai_vllm import OpenAIVLLM
from flo_ai.tool.base_tool import Tool


class LLMProvider(Enum):
    """Enum for supported LLM providers"""

    OPENAI = 'openai'
    GEMINI = 'gemini'
    ANTHROPIC = 'anthropic'
    VLLM = 'vllm'


class RootFloLLM(BaseLLM):
    """
    Proxy LLM class that routes to different SDK implementations based on type.
    Acts as a unified interface to OpenAI, Gemini, Anthropic SDKs and VLLM via a proxy URL.
    """

    def __init__(
        self,
        base_url: str,
        model_id: str,
        app_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        issuer: Optional[str] = None,
        audience: Optional[str] = None,
        access_token: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs,
    ):
        """
        Initialize RootFloLLM proxy.

        Args:
            base_url: The base URL of the proxy server
            model_id: The model identifier (config_id)
            app_key: Application key for X-Rootflo-Key header
            app_secret: Application secret for JWT signing
            issuer: JWT issuer claim
            audience: JWT audience claim
            access_token: Optional pre-generated access token (if provided, skips JWT generation)
            temperature: Temperature parameter for generation
            **kwargs: Additional parameters to pass to the underlying SDK

        Note:
            The actual LLM configuration is fetched lazily on first use (generate/stream)
            to avoid blocking HTTP calls during initialization.
        """
        # Validate required parameters
        if not model_id:
            raise ValueError('model_id is required')

        if not base_url:
            raise ValueError('base_url is required')

        # Store initialization parameters for lazy initialization
        self._base_url = base_url
        self._model_id = model_id
        self._app_key = app_key
        self._app_secret = app_secret
        self._issuer = issuer
        self._audience = audience
        self._access_token = access_token
        self._temperature = temperature
        self._kwargs = kwargs

        # Lazy initialization state
        self._llm = None
        self._initialized = False
        self._init_lock = asyncio.Lock()

        # Will be set during initialization
        self.base_url = base_url
        self.model_id = model_id
        self.llm_provider = None

        # Call parent __init__ with minimal parameters
        # Actual model will be set during lazy initialization
        super().__init__(
            model='',
            api_key='',
            temperature=temperature,
            **kwargs,
        )

    async def _fetch_llm_config_async(
        self,
        base_url: str,
        model_id: str,
        api_token: str | None = None,
        app_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch LLM configuration from the API endpoint asynchronously.

        Args:
            base_url: The base URL of the API server
            model_id: The model identifier (config_id)
            api_token: The JWT token for authorization
            app_key: Optional application key for X-Rootflo-Key header

        Returns:
            Dict containing llm_model and type

        Raises:
            Exception: If API call fails or response is invalid
        """
        config_url = f'{base_url}/v1/llm-inference-configs/{model_id}'

        headers = {}
        if api_token:
            headers['Authorization'] = f'Bearer {api_token}'

        # Only add X-Rootflo-Key header if app_key is provided
        if app_key:
            headers['X-Rootflo-Key'] = app_key

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(config_url, headers=headers, timeout=30.0)
                response.raise_for_status()

                data = response.json()

                config_data = data.get('data')
                if not config_data:
                    raise Exception('API response missing data field')

                llm_model = config_data.get('llm_model')
                llm_type = config_data.get('type')

                if not llm_model or not llm_type:
                    raise Exception(
                        f'API response missing required fields: llm_model={llm_model}, type={llm_type}'
                    )

                return {'llm_model': llm_model, 'type': llm_type}

        except httpx.HTTPStatusError as e:
            raise Exception(
                f'API request failed with status {e.response.status_code}: {e.response.text}'
            ) from e
        except httpx.RequestError as e:
            raise Exception(f'API request failed: {str(e)}') from e
        except Exception as e:
            raise Exception(f'Failed to fetch LLM config: {str(e)}') from e

    async def _ensure_initialized(self):
        """
        Ensure the LLM is initialized by fetching config on first use.
        Uses double-checked locking to prevent race conditions in concurrent scenarios.
        """
        # Fast path: already initialized
        if self._initialized:
            return

        # Acquire lock for initialization
        async with self._init_lock:
            # Double-check: another task might have initialized while we waited
            if self._initialized:
                return

            api_token = None
            # Generate or use provided access token
            if self._access_token:
                api_token = self._access_token
            elif self._app_key and self._app_secret:
                now = datetime.now()
                payload = {
                    'iss': self._issuer,
                    'aud': self._audience,
                    'iat': int(now.timestamp()),
                    'exp': int((now + timedelta(seconds=3600)).timestamp()),
                    'role_id': 'floconsole-service',
                    'user_id': 'service',
                    'service_auth': True,
                }
                service_token = jwt.encode(payload, self._app_secret, algorithm='HS256')
                api_token = f'fc_{service_token}'

            # Fetch LLM configuration from API
            config = await self._fetch_llm_config_async(
                self._base_url, self._model_id, api_token, self._app_key
            )
            llm_model = config['llm_model']
            llm_type = config['type']

            # Map type string to LLMProvider enum
            try:
                llm_provider = LLMProvider(llm_type.lower())
            except ValueError:
                raise ValueError(
                    f'Unsupported LLM provider type from API: {llm_type}. '
                    f'Supported types: {[p.value for p in LLMProvider]}'
                )

            # Update instance attributes
            self.llm_provider = llm_provider
            self.model = llm_model
            self.api_key = api_token

            # Construct full URL for LLM inference
            full_url = f'{self._base_url}/v1/llm-inference/{self._model_id}'

            # Prepare custom headers for proxy authentication (only if app_key is provided)
            custom_headers = {'X-Rootflo-Key': self._app_key} if self._app_key else {}

            # Instantiate appropriate SDK wrapper based on llm_provider
            if llm_provider == LLMProvider.OPENAI:
                self._llm = OpenAI(
                    model=llm_model,
                    base_url=full_url,
                    api_key=api_token or 'no_token',
                    temperature=self._temperature,
                    custom_headers=custom_headers,
                    **self._kwargs,
                )
            elif llm_provider == LLMProvider.ANTHROPIC:
                self._llm = Anthropic(
                    model=llm_model,
                    base_url=full_url,
                    api_key=api_token or 'no_token',
                    temperature=self._temperature,
                    custom_headers=custom_headers,
                    **self._kwargs,
                )
            elif llm_provider == LLMProvider.GEMINI:
                # Gemini SDK - pass base_url which will be handled via http_options
                self._llm = Gemini(
                    model=llm_model,
                    api_key=api_token or 'no_token',
                    temperature=self._temperature,
                    base_url=full_url,
                    custom_headers=custom_headers,
                    **self._kwargs,
                )
            elif llm_provider == LLMProvider.VLLM:
                # vLLM via OpenAI-compatible API
                self._llm = OpenAIVLLM(
                    model=llm_model,
                    base_url=full_url,
                    api_key=api_token or 'no_token',
                    temperature=self._temperature,
                    custom_headers=custom_headers,
                    **self._kwargs,
                )
            else:
                raise ValueError(f'Unsupported LLM provider: {llm_provider}')

            # Mark as initialized
            self._initialized = True

    async def generate(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate a response from the LLM"""
        await self._ensure_initialized()
        if self._llm is None:
            raise RuntimeError('LLM initialization failed: _llm is None')
        return await self._llm.generate(
            messages, functions=functions, output_schema=output_schema, **kwargs
        )

    async def stream(  # type: ignore[override]
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Generate a streaming response from the LLM"""
        await self._ensure_initialized()
        if self._llm is None:
            raise RuntimeError('LLM initialization failed: _llm is None')
        async for chunk in self._llm.stream(
            messages, functions=functions, output_schema=output_schema
        ):
            yield chunk

    def get_message_content(self, response: Any) -> str:
        """Extract message content from response"""
        if not getattr(self, '_initialized', False) or self._llm is None:
            raise RuntimeError(
                'RootFloLLM is not initialized yet; call generate() or stream() first.'
            )
        return self._llm.get_message_content(response)

    def format_tool_for_llm(self, tool: 'Tool') -> Dict[str, Any]:
        """Format a tool for the specific LLM's API"""
        if self._llm is None:
            raise RuntimeError('LLM initialization failed: _llm is None')
        return self._llm.format_tool_for_llm(tool)

    def format_tools_for_llm(self, tools: List['Tool']) -> List[Dict[str, Any]]:
        """Format a list of tools for the specific LLM's API"""
        if self._llm is None:
            raise RuntimeError('LLM initialization failed: _llm is None')
        return self._llm.format_tools_for_llm(tools)

    def format_image_in_message(self, image: ImageMessageContent) -> Any:
        """Format a image in the message"""
        if self._llm is None:
            raise RuntimeError('LLM initialization failed: _llm is None')
        return self._llm.format_image_in_message(image)
