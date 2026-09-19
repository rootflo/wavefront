import base64
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Mapping, Optional, Sequence

from bs4 import BeautifulSoup

from .types import EmailCapability, OutboundMessage

ScopeCatalog = Mapping[EmailCapability, List[str]]

# Provider scopes that include another capability's access. Catalogs list
# distinct OAuth scope strings, so exact matching alone would miss that
# gmail.modify / Mail.ReadWrite already cover read.
CAPABILITY_IMPLIES: Mapping[EmailCapability, frozenset[EmailCapability]] = {
    EmailCapability.MODIFY: frozenset({EmailCapability.READ}),
}


def resolve_scopes(
    catalog: ScopeCatalog,
    capabilities: Sequence[EmailCapability],
    identity_scopes: Sequence[str] = (),
) -> List[str]:
    """Flatten requested capabilities into a deduplicated scope list.

    Order is preserved so consent URLs stay stable between calls, which keeps
    them comparable in logs and tests.
    """
    scopes: List[str] = list(identity_scopes)
    for capability in capabilities:
        for scope in catalog.get(capability, []):
            if scope not in scopes:
                scopes.append(scope)
    return scopes


def capabilities_from_scopes(
    catalog: ScopeCatalog,
    granted_scopes: Optional[str],
) -> List[EmailCapability]:
    """Which capabilities a granted scope string satisfies.

    A capability counts as granted when every scope backing it is present, so a
    partially granted consent never reads as full permission. Capabilities that
    imply others (e.g. MODIFY → READ) are expanded afterward.
    """
    if not granted_scopes:
        return []
    granted = set(granted_scopes.split())
    matched = [
        capability
        for capability, required in catalog.items()
        if required and granted.issuperset(required)
    ]
    derived = set(matched)
    for capability in matched:
        derived.update(CAPABILITY_IMPLIES.get(capability, ()))
    # Preserve catalog declaration order for stable UI/API output.
    return [capability for capability in catalog if capability in derived]


def build_mime_message(sender: str, message: OutboundMessage) -> MIMEMultipart:
    """Assemble an RFC 822 message with an HTML body and binary attachments."""
    mime = MIMEMultipart()
    mime['to'] = ', '.join(message.to)
    mime['from'] = (
        f'{message.sender_display_name} <{sender}>'
        if message.sender_display_name
        else sender
    )
    mime['subject'] = message.subject
    mime.attach(MIMEText(message.body_html, 'html'))

    for attachment in message.attachments:
        maintype, subtype = _split_mime_type(attachment.mime_type)
        part = MIMEBase(maintype, subtype)
        part.set_payload(attachment.content_bytes)
        encoders.encode_base64(part)
        part.add_header(
            'Content-Disposition',
            f'attachment; filename="{attachment.file_name}"',
        )
        mime.attach(part)

    return mime


def _split_mime_type(mime_type: Optional[str]) -> tuple[str, str]:
    """Parse `type/subtype`, falling back to application/octet-stream."""
    raw = (mime_type or '').strip()
    if '/' in raw:
        maintype, subtype = raw.split('/', 1)
        maintype, subtype = maintype.strip(), subtype.strip()
        if maintype and subtype and ' ' not in maintype and ' ' not in subtype:
            return maintype, subtype
    return 'application', 'octet-stream'


def encode_raw_message(sender: str, message: OutboundMessage) -> str:
    """URL-safe base64 of the assembled MIME message, as Gmail's API expects."""
    return base64.urlsafe_b64encode(
        build_mime_message(sender, message).as_bytes()
    ).decode()


def build_graph_message(message: OutboundMessage) -> Dict[str, object]:
    """Microsoft Graph `sendMail` request body."""
    payload: Dict[str, object] = {
        'subject': message.subject,
        'body': {'contentType': 'HTML', 'content': message.body_html},
        'toRecipients': [
            {'emailAddress': {'address': recipient}} for recipient in message.to
        ],
    }
    if message.attachments:
        payload['attachments'] = [
            {
                '@odata.type': '#microsoft.graph.fileAttachment',
                'name': attachment.file_name,
                'contentType': attachment.mime_type or 'application/octet-stream',
                'contentBytes': base64.b64encode(attachment.content_bytes).decode(
                    'utf-8'
                ),
            }
            for attachment in message.attachments
        ]
    return payload


def html_to_text(html: str) -> str:
    """Readable plain text from an HTML body, for agents consuming the message."""
    return BeautifulSoup(html, 'html.parser').get_text(separator='\n').strip()
