import json
from urllib.parse import quote

import httpx

from tools_module.floware_api import FlowareApiClient


async def send_email(
    api: FlowareApiClient,
    /,
    connection_id: str,
    email_id: str,
    email_subject: str,
    email_body: str,
) -> str:
    """Send an email from a connected mailbox via wavefront's own REST API
    (POST /v1/email-connections/{connection_id}/send), so the tool never touches
    OAuth tokens.

    `connection_id` is prefilled server-side per selected tool; the model only
    supplies the recipient, subject and body.
    """
    url = (
        f'{api.base_url}/floware/v1/email-connections/'
        f'{quote(connection_id, safe="")}/send'
    )
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                json={
                    'to': [email_id],
                    'subject': email_subject,
                    'body': email_body,
                },
                headers=api.headers(),
                timeout=30.0,
            )
        except httpx.RequestError as e:
            return f'Failed to reach the email API: {e}'

    if response.status_code == 200:
        return f'Email sent to {email_id}.'

    error = _error_message(response)
    if response.status_code == 404:
        return f"Email connection '{connection_id}' not found"
    if response.status_code == 403:
        return error or 'This mailbox is not permitted to send email.'
    return error or f'Failed to send email ({response.status_code})'


def _error_message(response) -> str:
    """The API's own error text, or '' if the body is not the usual envelope."""
    try:
        return response.json().get('meta', {}).get('error') or ''
    except (json.JSONDecodeError, AttributeError, TypeError):
        return ''
