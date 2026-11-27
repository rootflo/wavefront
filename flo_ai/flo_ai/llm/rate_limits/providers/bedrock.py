"""AWS Bedrock (botocore) failures."""

from typing import Optional

import botocore.exceptions

from flo_ai.llm.rate_limits.models import Classification
from flo_ai.llm.rate_limits.providers.common import by_status

_THROTTLE_CODES = frozenset(
    {'ThrottlingException', 'TooManyRequestsException', 'Throttling'}
)


def classify_bedrock_error(exc: BaseException) -> Optional[Classification]:
    if isinstance(exc, botocore.exceptions.ClientError):
        code = exc.response.get('Error', {}).get('Code', '')
        status = exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode')
        if code in _THROTTLE_CODES or status == 429:
            return Classification('rate_limit', status or 429)
        return by_status(status)

    if isinstance(exc, botocore.exceptions.BotoCoreError):
        if isinstance(
            exc,
            (
                botocore.exceptions.ConnectionError,
                botocore.exceptions.HTTPClientError,
            ),
        ):
            return Classification('transient')
        return Classification('fatal')

    return None
