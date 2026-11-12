"""Image bytes for retrieve-API tests."""

import base64
import io

from PIL import Image


def jpeg_bytes(width: int = 8, height: int = 8) -> bytes:
    """A real JPEG whose header declares `width` x `height`.

    The image is encoded at 8x8 and its SOF0 frame header is then rewritten
    to the requested dimensions, so a 10,000 x 10,000 "decompression bomb"
    costs a few hundred bytes instead of hundreds of megabytes. The header is
    all the size check reads -- the pixels are never decoded.
    """
    buffer = io.BytesIO()
    Image.new('RGB', (8, 8), 'red').save(buffer, format='JPEG')
    data = bytearray(buffer.getvalue())
    sof = data.index(b'\xff\xc0')
    # FFC0, 2-byte length, 1-byte precision, then height and width.
    data[sof + 5 : sof + 7] = height.to_bytes(2, 'big')
    data[sof + 7 : sof + 9] = width.to_bytes(2, 'big')
    return bytes(data)


def image_bytes(image_format: str = 'PNG') -> bytes:
    """A small, real image in `image_format` (a Pillow format name)."""
    buffer = io.BytesIO()
    Image.new('RGB', (8, 8), 'red').save(buffer, format=image_format)
    return buffer.getvalue()


def jpeg_base64(width: int = 8, height: int = 8) -> str:
    return base64.b64encode(jpeg_bytes(width, height)).decode('ascii')


VALID_IMAGE_BASE64 = jpeg_base64()
