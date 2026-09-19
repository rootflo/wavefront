from typing import Any, Dict, List, Optional, Sequence, Union
from uuid import UUID

from common_module.log.logger import logger
from mailer import Attachment, EmailCapability, OutboundMessage

from plugins_module.services.email_connection_service import EmailConnectionService


class EmailSendService:
    """Outbound email for every caller: platform mail, scheduled jobs, agents.

    The sender is a connection, not configuration — an explicit `connection_id`
    when the caller has one, otherwise the primary connection.
    """

    def __init__(self, connection_service: EmailConnectionService):
        self._connections = connection_service

    async def send(
        self,
        subject: str,
        body_html: str,
        recipients: Union[str, Sequence[str]],
        attachments: Optional[Sequence[Union[Attachment, Dict[str, Any]]]] = None,
        connection_id: Optional[Union[str, UUID]] = None,
        sender_display_name: Optional[str] = None,
    ) -> bool:
        to = [recipients] if isinstance(recipients, str) else list(recipients)
        if not to:
            raise ValueError('At least one recipient is required')

        connection = await self._connections.resolve_sender(
            self._as_uuid(connection_id)
        )
        access_token, mailbox = await self._connections.get_access_token(
            connection.id, capabilities=[EmailCapability.SEND]
        )
        provider = await self._connections.get_provider(connection)

        message = OutboundMessage(
            subject=subject,
            body_html=body_html,
            to=to,
            attachments=self._normalize_attachments(attachments),
            sender_display_name=sender_display_name,
        )

        await provider.send_message(access_token, mailbox, message)
        logger.info(f'Email sent from {mailbox} to {len(to)} recipient(s)')
        return True

    @staticmethod
    def _as_uuid(connection_id: Optional[Union[str, UUID]]) -> Optional[UUID]:
        if connection_id is None or isinstance(connection_id, UUID):
            return connection_id
        return UUID(str(connection_id))

    @staticmethod
    def _normalize_attachments(
        attachments: Optional[Sequence[Union[Attachment, Dict[str, Any]]]],
    ) -> List[Attachment]:
        """Accept dict attachments as well as dataclasses.

        Report generation builds plain dicts, and requiring it to import the
        plugin's dataclass would push a provider concern into the job code.
        """
        if not attachments:
            return []

        normalized: List[Attachment] = []
        for attachment in attachments:
            if isinstance(attachment, Attachment):
                normalized.append(attachment)
                continue
            file_name = attachment.get('file_name') or attachment.get('filename')
            content = attachment.get('content_bytes') or attachment.get('content')
            if not file_name or content is None:
                raise ValueError('Attachment requires a file name and content bytes')
            normalized.append(
                Attachment(
                    file_name=file_name,
                    mime_type=attachment.get('mime_type') or 'application/octet-stream',
                    content_bytes=content,
                )
            )
        return normalized
