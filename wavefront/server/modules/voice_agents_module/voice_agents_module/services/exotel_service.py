import json
import os

import aiohttp
from common_module.log.logger import logger


class ExotelService:
    def __init__(self, call_processing_base_url: str):
        self.call_processing_base_url = call_processing_base_url

        if not self.call_processing_base_url:
            raise ValueError(
                'call_processing_base_url is required in voice_agents config'
            )

    async def initiate_call(
        self,
        to_number: str,
        from_number: str,
        voice_agent_id: str,
        api_key: str,
        api_token: str,
        account_sid: str,
        subdomain: str,
    ) -> dict:
        """
        Initiates an outbound call using Exotel v1 API

        Args:
            to_number: Destination phone number (E.164 format)
            from_number: Exotel virtual number (ExoPhone)
            voice_agent_id: ID of the voice agent
            api_key: Exotel API key
            api_token: Exotel API token
            account_sid: Exotel account SID
            subdomain: Exotel subdomain (e.g., api.exotel.com)

        Returns:
            dict: Call details including call_sid and status
        """
        try:
            # status_callback_url = f'{self.call_processing_base_url}/webhooks/exotel/status'

            # Construct Exotel v1 API endpoint (append .json for JSON response)
            endpoint = (
                f'https://{subdomain}/v1/Accounts/{account_sid}/Calls/connect.json'
            )
            auth = aiohttp.BasicAuth(api_key, api_token)
            timeout = aiohttp.ClientTimeout(total=15)

            app_id = os.getenv('EXOTEL_APP_ID')
            if not app_id:
                raise ValueError('EXOTEL_APP_ID environment variable is not set')

            exotel_url = (
                f'http://my.exotel.com/{account_sid}/exoml/start_voice/{app_id}'
            )

            # Build form data payload for v1 API
            payload = {
                'From': to_number,  # customer number
                # 'To': to_number,
                'Url': exotel_url,  # exotel app which will handle the call flow
                'CallerId': from_number,  # exotel number
                'CallType': 'trans',
                # 'StatusCallback': status_callback_url,
                # 'StatusCallbackEvents[0]': 'terminal',
                # 'StatusCallbackEvents[1]': 'answered',
                'CustomField': json.dumps({'voice_agent_id': voice_agent_id}),
            }

            masked_from = f'***{from_number[-4:]}'
            masked_to = f'***{to_number[-4:]}'
            logger.info(
                f'Initiating Exotel call from {masked_from} to {masked_to} for agent {voice_agent_id}'
            )

            # Make async API request
            async with aiohttp.ClientSession(timeout=timeout, auth=auth) as session:
                async with session.post(
                    endpoint,
                    data=payload,
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise ValueError(
                            f'Exotel API error: {response.status} - {error_text}'
                        )

                    response_data = await response.json()

                    call_details = response_data.get('Call', {})
                    call_sid = call_details.get('Sid')
                    status = call_details.get('Status')

                    logger.info(
                        f'Exotel call created successfully. Call SID: {call_sid}'
                    )

                    return {
                        'call_sid': call_sid,
                        'status': status,
                        'to_number': to_number,
                        'from_number': from_number,
                    }

        except Exception as e:
            logger.error(f'Failed to initiate Exotel call: {str(e)}')
            raise ValueError(f'Failed to initiate call with Exotel: {str(e)}')
