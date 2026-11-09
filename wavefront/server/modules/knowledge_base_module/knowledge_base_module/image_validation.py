"""Reject oversized images before they are sent to the inference service.

The inference service decodes every pixel of a query image before the
embedding models downscale it, so an image that is small on the wire but
declares huge dimensions (a decompression bomb) can exhaust its memory and
kill the worker mid-request. These checks read only the image header -- no
pixel data is decoded here -- so they cost almost nothing on any input.
"""

import base64
import binascii
import io
import warnings

from common_module.log.logger import logger
from common_module.utils.image_formats import (
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    SUPPORTED_PILLOW_FORMATS,
)
from PIL import Image

# Room for a data-URL prefix and MIME line wrapping on top of the base64 size
# of a MAX_IMAGE_BYTES image, so the string can be rejected before decoding.
_MAX_BASE64_CHARS = (MAX_IMAGE_BYTES + 2) // 3 * 4 + 64 * 1024

IMAGE_TOO_LARGE_MESSAGE = (
    f'Image exceeds the maximum allowed size of {MAX_IMAGE_BYTES // (1024 * 1024)} MB'
)
IMAGE_TOO_MANY_PIXELS_MESSAGE = (
    f'Image dimensions exceed the maximum of {MAX_IMAGE_PIXELS:,} pixels'
)
INVALID_BASE64_MESSAGE = 'Invalid base64 image data'
UNSUPPORTED_IMAGE_MESSAGE = 'Image data is not a supported image'


class ImageValidationError(ValueError):
    """The image must be rejected; the message is safe to return to the caller."""


def decode_base64_image(image_data: str) -> bytes:
    """Decode base64 image data, optionally prefixed as a data URL.

    Mirrors the inference service's parsing, so anything accepted here is
    accepted there.
    """
    if len(image_data) > _MAX_BASE64_CHARS:
        raise ImageValidationError(IMAGE_TOO_LARGE_MESSAGE)
    parts = image_data.split(',')
    base64_data = parts[1] if len(parts) == 2 else parts[0]
    try:
        return base64.b64decode(''.join(base64_data.split()), validate=True)
    except (binascii.Error, ValueError):
        raise ImageValidationError(INVALID_BASE64_MESSAGE)


def validate_image_bytes(image_bytes: bytes) -> None:
    """Raise ImageValidationError unless the image is within the size limits.

    `Image.open` parses only the header, so `size` is known without
    allocating the pixel buffer.
    """
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ImageValidationError(IMAGE_TOO_LARGE_MESSAGE)
    try:
        with warnings.catch_warnings():
            # Pillow warns for 89-179 MP; this check rejects those anyway.
            warnings.simplefilter('ignore', Image.DecompressionBombWarning)
            with Image.open(
                io.BytesIO(image_bytes), formats=SUPPORTED_PILLOW_FORMATS
            ) as image:
                width, height = image.size
    except Image.DecompressionBombError:
        # Pillow refuses past ~179 MP at open time.
        raise ImageValidationError(IMAGE_TOO_MANY_PIXELS_MESSAGE)
    except Exception as e:
        logger.warning(f'Rejected unreadable query image: {e}')
        raise ImageValidationError(UNSUPPORTED_IMAGE_MESSAGE)

    if width * height > MAX_IMAGE_PIXELS:
        logger.warning(f'Rejected query image of {width}x{height} pixels')
        raise ImageValidationError(IMAGE_TOO_MANY_PIXELS_MESSAGE)
