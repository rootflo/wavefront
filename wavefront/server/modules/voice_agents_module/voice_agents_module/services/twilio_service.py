from twilio.rest import Client as TwilioClient
from common_module.log.logger import logger


class TwilioService:
    def __init__(self, call_processing_base_url: str):
        self.call_processing_base_url = call_processing_base_url

        if not self.call_processing_base_url:
            raise ValueError(
                'call_processing_base_url is required in voice_agents config'
            )

    def initiate_call(
        self,
        to_number: str,
        from_number: str,
        voice_agent_id: str,
        account_sid: str,
        auth_token: str,
    ) -> dict:
        """
        Initiates an outbound call using Twilio

        Args:
            to_number: Destination phone number
            from_number: Source phone number (must be a Twilio number)
            voice_agent_id: ID of the voice agent
            account_sid: Twilio account SID
            auth_token: Twilio auth token

        Returns:
            dict: Call details including call_sid and status
        """
        try:
            # Create Twilio client
            client = TwilioClient(account_sid, auth_token)

            # Build TwiML URL that Twilio will call
            twiml_url = f'{self.call_processing_base_url}/webhooks/twiml?voice_agent_id={voice_agent_id}'

            logger.info(
                f'Initiating call from {from_number} to {to_number} for agent {voice_agent_id}'
            )

            # Create the call
            call = client.calls.create(
                to=to_number, from_=from_number, url=twiml_url, method='POST'
            )

            logger.info(f'Call created successfully. Call SID: {call.sid}')

            return {
                'call_sid': call.sid,
                'status': call.status,
                'to_number': to_number,
                'from_number': from_number,
            }

        except Exception as e:
            logger.error(f'Failed to initiate call: {str(e)}')
            raise ValueError(f'Failed to initiate call with Twilio: {str(e)}')
