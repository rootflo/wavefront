import aiohttp
from common_module.log.logger import logger


class SmartfloService:
    SMARTFLO_CLICK_TO_CALL_URL = (
        'https://api-smartflo.tatateleservices.com/v1/click_to_call_support'
    )

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
    ) -> dict:
        """
        Initiates an outbound call using Smartflo Click to Call API.

        Args:
            to_number: Destination phone number (customer number)
            from_number: Source phone number (agent outbound number)
            voice_agent_id: ID of the voice agent
            api_key: Smartflo API key

        Returns:
            dict: Call details including call_sid and status
        """
        try:
            if not api_key:
                raise ValueError('Missing Smartflo credentials: api_key')

            timeout = aiohttp.ClientTimeout(total=15)
            headers = {
                'accept': 'application/json',
                'content-type': 'application/json',
            }
            payload = {
                'async': 1,
                'api_key': api_key,
                'customer_number': to_number,
            }

            masked_from = f'***{from_number[-4:]}' if from_number else '****'
            masked_to = f'***{to_number[-4:]}' if to_number else '****'
            logger.info(
                f'Initiating Smartflo call from {masked_from} to {masked_to} '
                f'for agent {voice_agent_id}'
            )

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.SMARTFLO_CLICK_TO_CALL_URL,
                    json=payload,
                    headers=headers,
                ) as response:
                    result = await response.json()

                    if response.status != 200:
                        raise ValueError(
                            f'Smartflo API error ({response.status}): {result}'
                        )

                    call_sid = result.get('call_id', 'unknown')
                    logger.info(
                        f'Smartflo call created successfully. Call SID: {call_sid}'
                    )

                    return {
                        'call_sid': call_sid,
                        'status': 'call_initiated',
                        'to_number': to_number,
                        'from_number': from_number,
                    }

        except Exception as e:
            logger.error(f'Failed to initiate Smartflo call: {str(e)}')
            raise ValueError(f'Failed to initiate call with Smartflo: {str(e)}')
