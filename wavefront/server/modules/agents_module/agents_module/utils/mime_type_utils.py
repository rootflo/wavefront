"""MIME type gating for binary inference inputs.

The inference API accepts exactly two kinds of binary input: images and
documents. What flo-ai can actually *do* with them is narrower than what the
request schema allows, and the failure today happens deep inside the provider
call rather than at the boundary:

- Images reach the provider as an OpenAI-style ``image_url`` data URL
  (``AzureOpenAI.format_image_in_message``). Azure vision deployments read
  PNG, JPEG, GIF and WEBP; anything else is rejected by the API, and a missing
  mime type raises ``ValueError`` before the request is even built.
- Documents are rasterized to PNG pages by ``BaseLLM._rasterize_pdf_to_images``,
  which explicitly refuses any mime that is not a PDF.

So the supported set below is the Azure OpenAI capability set, which is what
this deployment targets. Providers with native document support (Anthropic,
Gemini, Vertex) accept more, but gating on the narrower set keeps a workflow
from succeeding on one agent's provider and failing on the next one's.
"""

import re
from typing import Optional, Tuple

from fastapi import HTTPException, status

SUPPORTED_IMAGE_MIME_TYPES = frozenset(
    {
        'image/png',
        'image/jpeg',
        'image/gif',
        'image/webp',
    }
)

SUPPORTED_DOCUMENT_MIME_TYPES = frozenset({'application/pdf'})

# Spellings clients send that mean one of the supported types above.
_MIME_ALIASES = {
    'image/jpg': 'image/jpeg',
    'image/pjpeg': 'image/jpeg',
    'application/x-pdf': 'application/pdf',
}

# Fallback when the caller sends raw base64 with no mime_type but does send a
# file name — common enough that rejecting it outright would be unhelpful.
# Deliberately includes unsupported formats too: resolving `report.docx` to its
# real mime is what lets the gate reject it with a useful message instead of
# waving it through as an unknown type.
_EXTENSION_TO_MIME = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'gif': 'image/gif',
    'webp': 'image/webp',
    'pdf': 'application/pdf',
    'bmp': 'image/bmp',
    'tif': 'image/tiff',
    'tiff': 'image/tiff',
    'svg': 'image/svg+xml',
    'heic': 'image/heic',
    'txt': 'text/plain',
    'csv': 'text/csv',
    'html': 'text/html',
    'json': 'application/json',
    'xml': 'application/xml',
    'doc': 'application/msword',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xls': 'application/vnd.ms-excel',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'ppt': 'application/vnd.ms-powerpoint',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}

_DATA_URL_PATTERN = re.compile(
    r'^data:(?P<mime>[a-zA-Z0-9][a-zA-Z0-9.+-]*/[a-zA-Z0-9][a-zA-Z0-9.+-]*)'
    r'(?P<params>;[^,]*)?,(?P<payload>.*)$',
    re.DOTALL,
)


def normalize_mime_type(mime_type: Optional[str]) -> Optional[str]:
    """Lowercase, strip any ``;charset=...`` suffix, and resolve aliases."""
    if not isinstance(mime_type, str):
        return None
    normalized = mime_type.split(';')[0].strip().lower()
    if not normalized:
        return None
    return _MIME_ALIASES.get(normalized, normalized)


def split_data_url(value: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Split a ``data:<mime>;base64,<payload>`` value into its two parts.

    Returns ``(None, None)`` for anything that is not a base64 data URL, so a
    caller can fall back to the value it already had. Non-base64 data URLs are
    deliberately not split: their payload is percent-encoded text, not base64,
    and handing that to a decoder would produce silent garbage.
    """
    if not isinstance(value, str):
        return None, None

    match = _DATA_URL_PATTERN.match(value)
    if not match:
        return None, None

    params = match.group('params') or ''
    if 'base64' not in params.lower():
        return None, None

    return normalize_mime_type(match.group('mime')), match.group('payload')


def mime_type_from_data_url(value: Optional[str]) -> Optional[str]:
    """Pull the mime type out of a ``data:<mime>;base64,...`` payload."""
    mime_type, _ = split_data_url(value)
    return mime_type


def mime_type_from_name(value: Optional[str]) -> Optional[str]:
    """Guess a mime type from a file name or URL path extension."""
    if not isinstance(value, str) or '.' not in value:
        return None
    # Drop query string / fragment before looking at the extension.
    path = value.split('?')[0].split('#')[0]
    extension = path.rsplit('.', 1)[-1].strip().lower()
    return _EXTENSION_TO_MIME.get(extension)


def resolve_mime_type(
    mime_type: Optional[str] = None,
    base64_value: Optional[str] = None,
    file_name: Optional[str] = None,
    url: Optional[str] = None,
) -> Optional[str]:
    """Best-effort mime type for a media input, most explicit source first."""
    return (
        normalize_mime_type(mime_type)
        or mime_type_from_data_url(base64_value)
        or mime_type_from_name(file_name)
        or mime_type_from_name(url)
    )


def _reject(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _position(index: Optional[int]) -> str:
    return f' at index {index}' if index is not None else ''


def ensure_supported_image_mime_type(
    mime_type: Optional[str] = None,
    base64_value: Optional[str] = None,
    file_name: Optional[str] = None,
    url: Optional[str] = None,
    index: Optional[int] = None,
) -> str:
    """Validate an image input's mime type, returning the resolved value.

    An unresolvable mime type is rejected rather than passed through: the
    provider needs it to build the data URL and would otherwise fail mid-run.
    """
    resolved = resolve_mime_type(mime_type, base64_value, file_name, url)
    supported = ', '.join(sorted(SUPPORTED_IMAGE_MIME_TYPES))

    if resolved is None:
        _reject(
            f'Could not determine the mime type of the image input{_position(index)}. '
            f'Send a `mime_type` field or a `data:<mime>;base64,` prefixed value. '
            f'Supported image types: {supported}'
        )

    if resolved not in SUPPORTED_IMAGE_MIME_TYPES:
        _reject(
            f'Unsupported image type `{resolved}`{_position(index)}. '
            f'Supported image types: {supported}'
        )

    return resolved


def ensure_supported_document_mime_type(
    mime_type: Optional[str] = None,
    base64_value: Optional[str] = None,
    file_name: Optional[str] = None,
    url: Optional[str] = None,
    index: Optional[int] = None,
) -> Optional[str]:
    """Validate a document input's mime type, returning the resolved value.

    Unlike images, an unresolvable mime type is allowed through: the document
    formatter treats a missing mime as ``application/pdf``, and callers have
    long sent raw PDF base64 with no mime type.
    """
    resolved = resolve_mime_type(mime_type, base64_value, file_name, url)
    supported = ', '.join(sorted(SUPPORTED_DOCUMENT_MIME_TYPES))

    if resolved is not None and resolved not in SUPPORTED_DOCUMENT_MIME_TYPES:
        _reject(
            f'Unsupported document type `{resolved}`{_position(index)}. '
            f'Supported document types: {supported}. '
            f'Convert the file to PDF, or send it as an image input.'
        )

    return resolved
