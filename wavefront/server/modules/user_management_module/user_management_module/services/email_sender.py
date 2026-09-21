from typing import Any, Dict, Optional, Protocol, Sequence, Union
from uuid import UUID


class EmailSender(Protocol):
    """What this module needs from whatever sends its mail.

    The implementation is `plugins_module`'s `EmailSendService`, which sends from
    a connected mailbox. Declared as a protocol here so user management does not
    import plugins_module: plugins_module already depends on this module.
    """

    async def send(
        self,
        subject: str,
        body_html: str,
        recipients: Union[str, Sequence[str]],
        attachments: Optional[Sequence[Dict[str, Any]]] = None,
        connection_id: Optional[Union[str, UUID]] = None,
        sender_display_name: Optional[str] = None,
    ) -> bool: ...
