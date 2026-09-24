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

Documents come in two kinds, and the distinction matters to the caller of this
module rather than to the gate itself:

- *Native* types reach the provider as a document block and are bounded by what
  the provider can parse -- today that is PDF alone.
- *Extractable* types are converted to text before they ever reach flo_ai (see
  ``document_text_extraction``), so they are bounded by what we can parse here,
  not by the provider. That is why Word, Excel and CSV are supported even though
  no provider this deployment targets accepts them.
"""

import re
from typing import Optional, Tuple

from fastapi import HTTPException, status

from agents_module.utils.document_text_extraction import (
    EXTRACTABLE_DOCUMENT_MIME_TYPES,
)

SUPPORTED_IMAGE_MIME_TYPES = frozenset(
    {
        'image/png',
        'image/jpeg',
        'image/gif',
        'image/webp',
    }
)

# Sent to the provider as a document block, as-is.
NATIVE_DOCUMENT_MIME_TYPES = frozenset({'application/pdf'})

SUPPORTED_DOCUMENT_MIME_TYPES = (
    NATIVE_DOCUMENT_MIME_TYPES | EXTRACTABLE_DOCUMENT_MIME_TYPES
)

# Spellings clients send that mean one of the supported types above.
_MIME_ALIASES = {
    'image/jpg': 'image/jpeg',
    'image/pjpeg': 'image/jpeg',
    'application/x-pdf': 'application/pdf',
    # Browsers and mail clients disagree on how to spell CSV. Note that Windows
    # reports `.csv` as `application/vnd.ms-excel`, which is indistinguishable
    # from a real legacy spreadsheet by mime alone -- that one is resolved from
    # the file's magic bytes in `document_text_extraction`, not here.
    'application/csv': 'text/csv',
    'text/comma-separated-values': 'text/csv',
    'application/vnd.msexcel': 'application/vnd.ms-excel',
}

# Fallback when the caller sends raw base64 with no mime_type but does send a
# file name — common enough that rejecting it outright would be unhelpful.
# Deliberately includes unsupported formats too (PowerPoint, SVG, HEIC):
# resolving `deck.pptx` to its real mime is what lets the gate reject it with a
# useful message instead of waving it through as an unknown type.
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

# Types that name a container rather than a format. Treated as weaker evidence
# than a file extension by `resolve_mime_type`; see the note there.
_GENERIC_MIME_TYPES = frozenset(
    {
        'application/octet-stream',
        'application/zip',
        'application/x-zip-compressed',
    }
)

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
    """Best-effort mime type for a media input, most explicit source first.

    A *generic* type is the exception to "most explicit first". A browser that
    cannot identify a file reports ``application/octet-stream``, and one that
    sees only the OOXML zip container reports ``application/x-zip-compressed``
    -- both routine on Windows for .docx and .xlsx. Those name a container, not
    a format, so `report.docx` is the better answer than either. Taking them
    literally rejects a file the extension gate had already accepted.

    That holds wherever the generic type appears: the declared field, or the
    prefix of a data URL. ``FileReader.readAsDataURL`` writes
    ``data:application/octet-stream;base64,`` for any file whose type the
    browser left empty, so a client passing its result straight through sends
    exactly that alongside `report.docx`.

    A generic type is still returned when nothing more specific exists, so an
    unidentifiable upload is rejected with its real type in the message, and a
    document with no resolvable type keeps failing open to PDF as before.
    """
    declared = normalize_mime_type(mime_type)
    from_data_url = mime_type_from_data_url(base64_value)
    for candidate in (declared, from_data_url):
        if candidate and candidate not in _GENERIC_MIME_TYPES:
            return candidate

    from_name = mime_type_from_name(file_name) or mime_type_from_name(url)
    return from_name or declared or from_data_url


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

    That fail-open is why callers must branch on the *returned* value rather
    than on "not a PDF" — ``None`` here means "assume PDF", and must never be
    routed to a text extractor.
    """
    resolved = resolve_mime_type(mime_type, base64_value, file_name, url)
    supported = ', '.join(sorted(SUPPORTED_DOCUMENT_MIME_TYPES))

    if resolved is not None and resolved not in SUPPORTED_DOCUMENT_MIME_TYPES:
        _reject(
            f'Unsupported document type `{resolved}`{_position(index)}. '
            f'Supported document types: {supported}. '
            f'Convert the file to one of those, or send it as an image input.'
        )

    return resolved
