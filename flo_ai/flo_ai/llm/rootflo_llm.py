from enum import Enum
from typing import AsyncIterator, Dict, Any, List, Optional
from datetime import datetime, timedelta
from flo_ai.models.chat_message import ImageMessageContent
import jwt
import httpx
from .base_llm import BaseLLM
from .openai_llm import OpenAI
from .gemini_llm import Gemini
from .anthropic_llm import Anthropic
from flo_ai.tool.base_tool import Tool


class LLMProvider(Enum):
    """Enum for supported LLM providers"""

    OPENAI = 'openai'
    GEMINI = 'gemini'
    ANTHROPIC = 'anthropic'


class RootFloLLM(BaseLLM):
    """
    Proxy LLM class that routes to different SDK implementations based on type.
    Acts as a unified interface to OpenAI, Gemini, and Anthropic SDKs via a proxy URL.
    """

    def __init__(
        self,
        base_url: str,
        model_id: str,
        app_key: str,
        app_secret: str,
        issuer: str,
        audience: str,
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
        """
        # Validate required parameters

        if not model_id:
            raise ValueError('model_id is required')

        if not base_url:
            raise ValueError('base_url is required')

        # Validate JWT credentials if access_token is not provided
        if not access_token:
            missing = []
            if not app_key:
                missing.append('app_key')
            if not app_secret:
                missing.append('app_secret')
            if not issuer:
                missing.append('issuer')
            if not audience:
                missing.append('audience')

            if missing:
                raise ValueError(
                    f'Missing required parameters for JWT generation: {", ".join(missing)}. '
                    f'Either provide these parameters or pass an access_token directly.'
                )
        else:  # app key is still required
            if not app_key:
                raise ValueError('app_key is required even when using access_token')

        # Use provided access_token or generate JWT token
        if access_token:
            api_token = access_token
        else:
            now = datetime.now()
            payload = {
                'iss': issuer,
                'aud': audience,
                'iat': int(now.timestamp()),
                'exp': int((now + timedelta(seconds=3600)).timestamp()),
                'role_id': 'floconsole-service',
                'user_id': 'service',
                'service_auth': True,
            }
            service_token = jwt.encode(payload, app_secret, algorithm='HS256')
            api_token = f'fc_{service_token}'

        # Fetch LLM configuration from API
        config = self._fetch_llm_config(base_url, model_id, api_token, app_key)
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

        super().__init__(
            model=llm_model, api_key=api_token, temperature=temperature, **kwargs
        )

        self.base_url = base_url
        self.model_id = model_id
        self.llm_provider = llm_provider

        # Construct full URL for LLM inference
        full_url = f'{base_url}/v1/llm-inference/{model_id}'

        # Prepare custom headers for proxy authentication
        custom_headers = {'X-Rootflo-Key': app_key}

        # Instantiate appropriate SDK wrapper based on llm_provider
        if llm_provider == LLMProvider.OPENAI:
            self._llm = OpenAI(
                model=llm_model,
                base_url=full_url,
                api_key=api_token,
                temperature=temperature,
                custom_headers=custom_headers,
                **kwargs,
            )
        elif llm_provider == LLMProvider.ANTHROPIC:
            self._llm = Anthropic(
                model=llm_model,
                base_url=full_url,
                api_key=api_token,
                temperature=temperature,
                custom_headers=custom_headers,
                **kwargs,
            )
        elif llm_provider == LLMProvider.GEMINI:
            # Gemini SDK - pass base_url which will be handled via http_options
            self._llm = Gemini(
                model=llm_model,
                api_key=api_token,
                temperature=temperature,
                base_url=full_url,
                custom_headers=custom_headers,
                **kwargs,
            )
        else:
            raise ValueError(f'Unsupported LLM provider: {llm_provider}')

    def _fetch_llm_config(
        self, base_url: str, model_id: str, api_token: str, app_key: str
    ) -> Dict[str, Any]:
        """
        Fetch LLM configuration from the API endpoint.

        Args:
            base_url: The base URL of the API server
            model_id: The model identifier (config_id)
            api_token: The JWT token for authorization
            app_key: Application key for X-Rootflo-Key header

        Returns:
            Dict containing llm_model and type

        Raises:
            Exception: If API call fails or response is invalid
        """
        config_url = f'{base_url}/v1/llm-inference-configs/{model_id}'
        headers = {
            'Authorization': f'Bearer {api_token}',
            'X-Rootflo-Key': app_key,
        }

        try:
            with httpx.Client() as client:
                response = client.get(config_url, headers=headers, timeout=30.0)
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

    async def generate(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate a response from the LLM"""
        return await self._llm.generate(
            messages, functions=functions, output_schema=output_schema, **kwargs
        )

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        functions: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Generate a streaming response from the LLM"""
        async for chunk in self._llm.stream(messages, functions=functions, **kwargs):
            yield chunk

    def get_message_content(self, response: Any) -> str:
        """Extract message content from response"""
        return self._llm.get_message_content(response)

    def format_tool_for_llm(self, tool: 'Tool') -> Dict[str, Any]:
        """Format a tool for the specific LLM's API"""
        return self._llm.format_tool_for_llm(tool)

    def format_tools_for_llm(self, tools: List['Tool']) -> List[Dict[str, Any]]:
        """Format a list of tools for the specific LLM's API"""
        return self._llm.format_tools_for_llm(tools)

    def format_image_in_message(self, image: ImageMessageContent) -> str:
        """Format a image in the message"""
        return self._llm.format_image_in_message(image)
