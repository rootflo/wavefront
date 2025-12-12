from dataclasses import dataclass

# from floconsole.constants.app import AppDeploymentType
from floconsole.constants.auth import RootfloHeaders
import httpx
import os
from fastapi import Request
from fastapi.responses import Response, StreamingResponse

from floconsole.services.token_service import TokenService
from floconsole.services.app_service import AppService


@dataclass
class UserSession:
    role_id: str
    user_id: str
    session_id: str


class FlowareProxyService:
    def __init__(
        self,
        token_service: TokenService,
        app_service: AppService,
        service_issuer: str = 'https://console.rootflo.ai',
        app_env: str = 'production',
        token_prefix: str = 'fc_',
        temporary_token_expiry: int = 300,
    ):
        self.token_service = token_service
        self.app_service = app_service
        self.service_issuer = service_issuer
        self.is_dev = app_env == 'dev'
        self.app_env = app_env
        self.token_prefix = token_prefix
        self.temporary_token_expiry = int(temporary_token_expiry)
        self.passthrough_secret = os.getenv('PASSTHROUGH_SECRET')

    async def _get_app_base_url(self, private_url: str, app_id: str) -> str:
        """Get app base URL - used for both floware URL and JWT audience"""
        if private_url.startswith('http'):
            return private_url.rstrip('/')
        elif self.is_dev and 'localhost' in app_id:
            return f'http://{app_id}'
        elif self.is_dev and 'host.docker.internal' in app_id:
            return f'http://{app_id}'
        else:
            return private_url.rstrip('/')

    async def proxy_request(
        self, method: str, app_id: str, path: str, request: Request
    ) -> Response:
        """
        Proxy request to floware service with service authentication

        Flow:
        1. Get user session from middleware (already validated)
        2. Fetch app details from database using app_id
        3. Generate T2 service token with app-specific secret
        4. Forward request to floware with app-specific key + Authorization headers
        5. Return floware response directly
        """
        # Step 1: Get user session from middleware (already validated)
        # session = request.state.session

        # Step 2: Fetch app details from database
        try:
            app = await self.app_service.get_app_by_id(app_id)
            if not app:
                raise ValueError(f'App not found for ID: {app_id}')
        except ValueError as e:
            if 'App not found' in str(e):
                raise e
            raise ValueError(f'Invalid app_id format: {app_id}')

        # if app.deployment_type == AppDeploymentType.MANUAL.value:
        #     app_base_url = await self._get_app_base_url(app.private_url, app_id)
        # else:
        #     app_base_url = await self._get_app_base_url(
        #         'https://' + app.app_name + '-floware.apps.rootflo.ai', app_id
        #     )

        app_base_url = await self._get_app_base_url(app.private_url, app_id)

        # Step 3: Prepare request to floware
        floware_url = f'{app_base_url}/floware/{path}'

        # Copy headers from original request, excluding Authorization
        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() not in ['authorization', 'host', 'content-length']
        }

        headers['Content-Type'] = request.headers.get(
            'Content-Type', 'application/json'
        )

        # Step 4: Add passthrough header for non-production environments
        if self.app_env != 'production' and self.passthrough_secret:
            headers[RootfloHeaders.PASSTHROUGH] = self.passthrough_secret

        # Copy query parameters
        query_params = dict(request.query_params)

        # Step 5: Detect if streaming (SSE) is needed
        is_streaming = 'text/event-stream' in request.headers.get('accept', '').lower()

        # Step 6: Make request to floware
        if is_streaming:
            # Streaming path: Keep client and stream contexts alive during iteration
            client = httpx.AsyncClient(timeout=120.0)

            # Start the stream context
            stream_context = client.stream(
                method=method,
                url=floware_url,
                headers=headers,
                content=request.stream()
                if method in ['POST', 'PUT', 'PATCH', 'DELETE']
                else None,
                params=query_params,
            )

            # Enter the stream context to get response metadata
            response = await stream_context.__aenter__()

            # Extract headers and status before streaming
            response_headers = {
                key: value
                for key, value in response.headers.items()
                if key.lower()
                not in ['content-length', 'transfer-encoding', 'connection']
            }
            status_code = response.status_code

            # Create generator that streams and cleans up contexts when done
            async def stream_generator():
                try:
                    async for chunk in response.aiter_bytes():
                        yield chunk
                finally:
                    # Clean up stream context and client when streaming completes
                    await stream_context.__aexit__(None, None, None)
                    await client.aclose()

            return StreamingResponse(
                stream_generator(),
                status_code=status_code,
                headers=response_headers,
                media_type=response.headers.get('content-type', 'text/event-stream'),
            )

        # Non-streaming path: Use context manager for automatic cleanup
        async with httpx.AsyncClient(timeout=600.0) as client:
            # Non-streaming path: Buffer entire response (backward compatible)
            response = await client.request(
                method=method,
                url=floware_url,
                headers=headers,
                content=request.stream()
                if method in ['POST', 'PUT', 'PATCH', 'DELETE']
                else None,
                params=query_params,
            )

            # Return floware response directly - let floware handle JSON formatting
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers={
                    key: value
                    for key, value in response.headers.items()
                    if key.lower()
                    not in ['content-length', 'transfer-encoding', 'connection']
                },
            )
