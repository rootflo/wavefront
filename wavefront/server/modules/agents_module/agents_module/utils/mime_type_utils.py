"""MIME type gating for binary inference inputs.

The inference API accepts exactly two kinds of binary input: images and
documents. What flo-ai can actually *do* with them is narrower than what the
request schema allows, and the failure today happens deep inside the provider
call rather than at the boundary:

- Images are formatted as an OpenAI-style ``image_url`` data URL, which the
  vision APIs accept as PNG, JPEG, GIF or WEBP. Anything else is rejected by
  the provider, and a missing mime type raises ``ValueError`` before the
  request is even built.
- Documents are rasterized to PNG pages by ``BaseLLM._rasterize_pdf_to_images``,
  which explicitly refuses any mime that is not a PDF.

The supported set below is therefore the intersection of what the providers
accept, not the union. Some providers handle more formats natively, but an
agent's provider is a property of its configuration: gating on the union would
let a workflow succeed on one agent and fail on the next for reasons the
caller cannot see. The narrow set fails the same way everywhere, at the
boundary, with an error naming the offending input.
"""

import base64
import binascii
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

# Everything above resolves a mime type from *metadata* — the `mime_type`
# field, the `data:` prefix, the file name, the URL — and every one of those is
# written by the caller. A PHP script sent as `mime_type: image/png` with
# `file_name: shell.php` satisfies all of them.
#
# These are the formats' own self-identification, at a fixed offset, which the
# caller cannot fake without actually sending a file of that type. A payload
# whose bytes disagree with its declared type is rejected.
_MAGIC_SIGNATURES = (
    (0, b'\x89PNG\r\n\x1a\n', 'image/png'),
    (0, b'\xff\xd8\xff', 'image/jpeg'),
    (0, b'GIF87a', 'image/gif'),
    (0, b'GIF89a', 'image/gif'),
    (0, b'%PDF-', 'application/pdf'),
)

# WEBP is the one supported format that needs two checks: 'RIFF' at 0, then
# 'WEBP' at 8 with the file size in between.
_WEBP_PREFIX = b'RIFF'
_WEBP_FORMAT = b'WEBP'

# Enough for every signature above, including WEBP's byte 8-11. Read from the
# front of the payload only — a whole multi-megabyte upload never gets decoded
# twice just to identify it.
_HEADER_BYTES = 24
_HEADER_B64_CHARS = (_HEADER_BYTES // 3) * 4

_DATA_URL_PATTERN = re.compile(
    r'^data:(?P<mime>[a-zA-Z0-9][a-zA-Z0-9.+-]*/[a-zA-Z0-9][a-zA-Z0-9.+-]*)'
    r'(?P<params>;[^,]*)?,(?P<payload>.*)$',
    re.DOTALL,
)

# `file_name` is scrubbed before it becomes a storage key, but it is also
# stored verbatim and returned by the execution-read endpoints for clients to
# render as a file list. A genuine image named `<img src=x onerror=...>.png`
# passes every content check and still reaches the consumer's DOM.
#
# Blocked rather than allow-listed: an ASCII allow-list would reject any
# non-Latin filename. These are the characters that let a name break out of
# the context it is rendered in — HTML, a log line, a quoted header value.
#
# Path separators are deliberately *not* blocked. A folder upload legitimately
# sends `folder/subfolder/report.pdf`, and a separator is harmless in a string
# meant to be displayed. Nothing derives a path from this value: the storage key
# is built by _safe_filename, which scrubs separately and far more strictly.
_UNSAFE_FILE_NAME_CHARS = re.compile(r'[<>"\'&\x00-\x1f\x7f]')
MAX_FILE_NAME_LENGTH = 255


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


def detect_mime_type_from_bytes(data: Optional[bytes]) -> Optional[str]:
    """Identify a payload from its magic bytes, or None if unrecognised.

    Only the formats this API accepts are recognised. Anything else — a script,
    an archive, an office document — returns None and is rejected by the
    callers below rather than being named, since naming it would imply support.
    """
    if not data:
        return None

    for offset, signature, mime_type in _MAGIC_SIGNATURES:
        if data[offset : offset + len(signature)] == signature:
            return mime_type

    if data[:4] == _WEBP_PREFIX and data[8:12] == _WEBP_FORMAT:
        return 'image/webp'

    return None


def _decode_header(base64_value: Optional[str]) -> Optional[bytes]:
    """Decode just enough of a base64 payload to read its magic bytes."""
    if not isinstance(base64_value, str):
        return None

    _, stripped = split_data_url(base64_value)
    payload = stripped if stripped is not None else base64_value

    # Base64 in the wild arrives line-wrapped; join it before slicing so the
    # chunk boundary lands on a real 4-character group.
    compact = ''.join(payload.split())
    chunk = compact[:_HEADER_B64_CHARS]
    chunk = chunk[: len(chunk) - len(chunk) % 4]
    if not chunk:
        return None

    try:
        return base64.b64decode(chunk, validate=True)
    except (binascii.Error, ValueError):
        # Undecodable base64 is rejected further down the pipeline, where the
        # error names the offending input. Not this function's job.
        return None


def ensure_bytes_match_mime_type(
    declared_mime_type: str,
    base64_value: Optional[str],
    index: Optional[int] = None,
) -> None:
    """Reject a payload whose actual content contradicts its declared type.

    This is what stops a script being accepted as an image: the declared type,
    the file name and the `data:` prefix are all caller-written, but the magic
    bytes are the file itself.

    Inputs supplied by URL, path or raw bytes carry no base64 to inspect and
    are left alone — there is nothing here to check.
    """
    header = _decode_header(base64_value)
    if header is None:
        return

    actual = detect_mime_type_from_bytes(header)

    if actual is None:
        _reject(
            f'The content of the file{_position(index)} is not a supported '
            f'file type. It was declared as `{declared_mime_type}`, but its '
            f'contents do not match that or any other accepted format.'
        )

    if actual != declared_mime_type:
        _reject(
            f'File content does not match its declared type{_position(index)}: '
            f'declared `{declared_mime_type}`, but the contents are `{actual}`.'
        )


def ensure_safe_file_name(
    file_name: Optional[str],
    index: Optional[int] = None,
) -> Optional[str]:
    """Reject a file name that could not be rendered as text safely.

    The name travels further than the bytes do: it is persisted and returned
    by the execution-read endpoints, so it has to be safe for a consumer to
    display, not merely safe to store.
    """
    if file_name is None:
        return None

    if not isinstance(file_name, str):
        _reject(
            f'Invalid file name{_position(index)}: expected a string, '
            f'got {type(file_name).__name__}'
        )

    if len(file_name) > MAX_FILE_NAME_LENGTH:
        _reject(
            f'File name too long{_position(index)}: {len(file_name)} '
            f'characters, limit is {MAX_FILE_NAME_LENGTH}.'
        )

    if _UNSAFE_FILE_NAME_CHARS.search(file_name):
        _reject(
            f'Invalid file name{_position(index)}: angle brackets, quotes, '
            f'ampersands and control characters are not allowed.'
        )

    return file_name


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

    # Everything checked so far was the caller's own description of the file.
    ensure_bytes_match_mime_type(resolved, base64_value, index)

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

    # An unresolvable document mime is still allowed through above, because the
    # formatter defaults it to PDF — so check the bytes against PDF, not
    # against the declaration that was never made.
    ensure_bytes_match_mime_type(resolved or 'application/pdf', base64_value, index)

    return resolved
