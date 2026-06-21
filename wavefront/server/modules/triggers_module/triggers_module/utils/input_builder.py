import base64
from typing import Any, Dict, List, Optional, Sequence

from common_module.log.logger import logger

from triggers_module.providers.base import NormalizedEmailEvent


DEFAULT_ALLOWED_MIME_TYPES = (
    'application/pdf',
    'text/plain',
    'text/csv',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'image/png',
    'image/jpeg',
    'image/jpg',
)


class EmailTooLargeError(Exception):
    pass


def build_inference_inputs(
    event: NormalizedEmailEvent,
    allowed_mime_types: Optional[Sequence[str]] = None,
    max_total_bytes: int = 25 * 1024 * 1024,
) -> List[Dict[str, Any]]:
    """Produce the v3-inference `inputs` list for a normalized email.

    Order: each accepted attachment (base64-encoded) first, body text last.
    Drops attachments outside `allowed_mime_types`. Raises EmailTooLargeError
    if total attachment bytes exceed `max_total_bytes`.
    """
    allowed = set(allowed_mime_types or DEFAULT_ALLOWED_MIME_TYPES)

    total_bytes = 0
    inputs: List[Dict[str, Any]] = []

    for attachment in event.attachments:
        if attachment.mime_type not in allowed:
            logger.debug(
                f'Skipping attachment {attachment.file_name} '
                f'(mime_type={attachment.mime_type} not in allowlist)'
            )
            continue

        total_bytes += len(attachment.content_bytes)
        if total_bytes > max_total_bytes:
            raise EmailTooLargeError(
                f'Email attachments exceed {max_total_bytes} bytes total'
            )

        encoded = base64.b64encode(attachment.content_bytes).decode('utf-8')
        inputs.append(
            {
                'role': 'user',
                'content': {
                    'document_base64': encoded,
                    'mime_type': attachment.mime_type,
                    'file_name': attachment.file_name,
                },
            }
        )

    inputs.append({'role': 'user', 'content': event.body_text or ''})
    return inputs
