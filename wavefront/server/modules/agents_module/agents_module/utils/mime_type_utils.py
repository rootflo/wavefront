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

Documents come in two kinds:

- *Native* types reach the provider as a document block and are bounded by what
  the provider can parse -- today that is PDF alone.
- *Extractable* types are converted to text by flo_ai when it formats the
  message (``flo_ai.utils.document_text_extraction``), so they are bounded by
  what flo_ai can parse, not by the provider. That is why Word, Excel and CSV
  are supported even though no provider this deployment targets accepts them.
  The set is imported from flo_ai rather than restated here, so this gate
  cannot admit a type flo_ai does not know how to handle.
"""

import base64
import binascii
import re
from io import BytesIO
from itertools import islice
from typing import Optional, Tuple

import pymupdf
from fastapi import HTTPException, status

from flo_ai.utils.document_text_extraction import (
    EXTRACTABLE_DOCUMENT_MIME_TYPES,
)
from PIL import Image

from common_module.log.logger import logger

# What is safe to log here is metadata about the check, never the file itself.
# The base64, the decoded bytes and `file_name` are all off limits — the first
# two are the document's contents and the third routinely carries PII (a
# claimant's name, a policy number). Byte size, page count, resolved format and
# the input's index disclose none of that.

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
    # the file's magic bytes in flo_ai's document_text_extraction.
    'application/csv': 'text/csv',
    'text/comma-separated-values': 'text/csv',
    'application/vnd.msexcel': 'application/vnd.ms-excel',
    # Legacy Word. Harmless while .doc is deferred -- the alias resolves to a
    # type the gate still rejects -- and correct once flo_ai enables it.
    'application/vnd.ms-word': 'application/msword',
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

# Bounds the pixel buffer a single image decode may allocate. The structural
# gate calls load(), which decodes every pixel, so an image that declares
# enormous dimensions is a memory-exhaustion vector. Deliberately stricter than
# Pillow's ~89 MP default, which only *warns* up to twice that before it
# raises — this is the hard ceiling, checked before load() allocates anything.
# Generous for real inputs: a 40 MP image is larger than any current phone
# camera produces.
MAX_IMAGE_PIXELS = 40_000_000

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

    # Base64 in the wild arrives line-wrapped, so the newlines have to come out
    # before the chunk boundary can land on a real 4-character group. Consumed
    # lazily and stopped at the header: stripping the whole string first cost
    # a full copy of a multi-megabyte payload to read twenty-four bytes.
    chars = list(islice((c for c in payload if not c.isspace()), _HEADER_B64_CHARS))

    usable = len(chars) - len(chars) % 4
    if not usable:
        return None

    try:
        return base64.b64decode(''.join(chars[:usable]), validate=True)
    except (binascii.Error, ValueError):
        # Undecodable base64 is rejected further down the pipeline, where the
        # error names the offending input. Not this function's job.
        return None


def _decode_base64_payload(
    base64_value: Optional[str], index: Optional[int] = None
) -> Optional[bytes]:
    """Decode a whole base64 payload for the structural parser.

    Returns None only when there is nothing to decode — a URL, path or bytes
    input carries no base64, and the caller skips its parser for those. A
    payload that IS present but does not decode is rejected here, not returned
    as None: conflating the two let malformed base64 slip past the structural
    parse and be accepted on an input the gate never actually inspected.

    Unlike _decode_header this returns every byte, because the parser needs the
    whole file. Whitespace is stripped first: line-wrapped base64 is common and
    ``validate=True`` treats a newline as an illegal character.
    """
    if not isinstance(base64_value, str):
        return None

    _, stripped = split_data_url(base64_value)
    payload = stripped if stripped is not None else base64_value

    try:
        return base64.b64decode(''.join(payload.split()), validate=True)
    except (binascii.Error, ValueError):
        _reject(f'Invalid file format{_position(index)}.')


def _ensure_decodable_image(data: bytes, index: Optional[int]) -> None:
    """Reject image bytes that a real decoder cannot read as an image.

    The magic-byte check confirms the file *starts* like a supported image;
    this confirms it *is* one. A payload that is only a signature followed by
    other content — `GIF89a` then a script — passes the former and fails here.

    verify() checks the file's structure but does not decode its pixels, so a
    GIF — and some JPEGs — with a valid header but undecodable image data pass
    it and only fail later, inside the provider call. load() decodes for real
    and catches those at the boundary.
    """
    try:
        with Image.open(BytesIO(data)) as image:
            # Read the format before verify(), which leaves the object unusable.
            image_format = image.format
            image.verify()

        # verify() spends the object, so reopen to decode the pixels. The
        # declared dimensions are checked before load() allocates the buffer:
        # Pillow only warns between its bomb threshold and twice that, and on a
        # full decode that band is hundreds of megabytes — this cap is the hard
        # limit, enforced before any allocation.
        with Image.open(BytesIO(data)) as image:
            pixels = image.size[0] * image.size[1]
            if pixels > MAX_IMAGE_PIXELS:
                raise ValueError(f'image exceeds the {MAX_IMAGE_PIXELS}-pixel limit')
            image.load()
    except Exception:
        # A validation boundary fails closed: any reason the decoder could not
        # read the file — an unknown format, a truncated stream, undecodable
        # pixels, a size past the pixel cap — is a rejection, not a 500. The
        # message stays generic on purpose: naming what failed hands a prober
        # information about the check it is trying to get past.
        logger.warning(
            f'Rejected image input{_position(index)}: '
            f'not a decodable image, {len(data)} bytes'
        )
        _reject(f'Invalid file format{_position(index)}.')

    logger.info(
        f'Validated image input{_position(index)}: '
        f'{image_format}, {len(data)} bytes'
    )


def _ensure_decodable_pdf(data: bytes, index: Optional[int]) -> None:
    """Reject document bytes that are not a structurally valid PDF.

    ``%PDF-`` as a prefix is not a PDF any more than `GIF89a` is a GIF: a real
    PDF has a cross-reference table and at least one page object. Opening it
    with the parser and reading the page count forces that structure to exist.
    """
    try:
        with pymupdf.open(stream=data, filetype='pdf') as document:
            page_count = document.page_count
            if page_count < 1:
                raise ValueError('PDF has no pages')
    except Exception:
        logger.warning(
            f'Rejected document input{_position(index)}: '
            f'not a parseable PDF, {len(data)} bytes'
        )
        _reject(f'Invalid file format{_position(index)}.')

    logger.info(
        f'Validated document input{_position(index)}: '
        f'PDF, {page_count} pages, {len(data)} bytes'
    )


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
        logger.warning(
            f'Rejected input{_position(index)}: declared `{declared_mime_type}` '
            f'but the content matches no supported format'
        )
        _reject(
            f'The content of the file{_position(index)} is not a supported '
            f'file type. It was declared as `{declared_mime_type}`, but its '
            f'contents do not match that or any other accepted format.'
        )

    if actual != declared_mime_type:
        logger.warning(
            f'Rejected input{_position(index)}: declared `{declared_mime_type}` '
            f'but the content is `{actual}`'
        )
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

    # Everything checked so far was the caller's own description of the file,
    # then its first few bytes. The final check parses the whole thing: magic
    # bytes prove a prefix, not a valid image.
    ensure_bytes_match_mime_type(resolved, base64_value, index)

    data = _decode_base64_payload(base64_value, index)
    if data is not None:
        _ensure_decodable_image(data, index)

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

    Extractable types sent only as ``document_url`` are rejected too. flo_ai
    extracts their text from the file bytes and deliberately does not download
    URLs, so accepting one here only moves the failure to the provider call --
    after a 202 on the async endpoints.
    """
    resolved = resolve_mime_type(mime_type, base64_value, file_name, url)
    supported = ', '.join(sorted(SUPPORTED_DOCUMENT_MIME_TYPES))

    if resolved is not None and resolved not in SUPPORTED_DOCUMENT_MIME_TYPES:
        _reject(
            f'Unsupported document type `{resolved}`{_position(index)}. '
            f'Supported document types: {supported}. '
            f'Convert the file to one of those, or send it as an image input.'
        )

    if resolved in EXTRACTABLE_DOCUMENT_MIME_TYPES and url and not base64_value:
        _reject(
            f'Document type `{resolved}`{_position(index)} cannot be sent as '
            f'`document_url`. Send the file contents as `document_base64`.'
        )

    # An unresolvable document mime is still allowed through above, because the
    # formatter defaults it to PDF — so check the bytes against PDF, not
    # against the declaration that was never made.
    ensure_bytes_match_mime_type(resolved or 'application/pdf', base64_value, index)

    data = _decode_base64_payload(base64_value, index)
    if data is not None:
        _ensure_decodable_pdf(data, index)

    # An unresolvable document mime is still allowed through above, because the
    # formatter defaults it to PDF — so check the bytes against PDF, not
    # against the declaration that was never made.
    ensure_bytes_match_mime_type(resolved or 'application/pdf', base64_value, index)

    data = _decode_base64_payload(base64_value, index)
    if data is not None:
        _ensure_decodable_pdf(data, index)

    return resolved
