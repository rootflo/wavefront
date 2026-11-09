"""The set of image formats Pillow is allowed to decode.

Pillow picks a decoder by sniffing the file's magic bytes, not by trusting a
declared mime type, so a mime gate at the API boundary does not constrain which
decoder actually runs. Every Pillow CVE this codebase has been flagged for --
CVE-2026-25990 and -42311 (PSD), -40192 (FITS), -54058 (McIdas AREA), -59204
(JPEG2000) -- lives in a decoder for a format the product never intentionally
handles. Passing this tuple as ``Image.open(..., formats=...)`` is what keeps
those decoders out of reach of an uploaded byte string.

Deliberately wider than ``SUPPORTED_IMAGE_MIME_TYPES`` in
``agents_module.utils.mime_type_utils`` (png/jpeg/gif/webp): that gate covers a
different API and reflects what Azure vision can read, whereas BMP and TIFF are
needed here because ``inference_app.utils.image_utils`` exists precisely as a
fallback for images OpenCV could not decode.

An input outside this set raises ``PIL.UnidentifiedImageError``, the same error
Pillow already raises for unrecognised bytes, so callers need no new handling.
"""

SUPPORTED_PILLOW_FORMATS = ('JPEG', 'PNG', 'GIF', 'WEBP', 'BMP', 'TIFF')

# Hard ceilings for an image sent to a service that decodes it. Compressed size
# says little about decoded size -- a 1.5 MB solid-colour JPEG can declare
# 10,000 x 10,000 pixels, ~300 MB once decoded to RGB -- so the pixel count is
# checked from the header, before anything decodes. Pillow's own
# decompression-bomb guard only warns below ~179 MP, so it is not enough.
# 40 MP is larger than any current phone camera produces, and the embedding
# models downscale to a few hundred pixels anyway.
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_BYTES = 10 * 1024 * 1024

# Mime types for the formats above, for rejecting an upload before its bytes
# are shipped to a service that decodes with SUPPORTED_PILLOW_FORMATS.
SUPPORTED_PILLOW_MIME_TYPES = frozenset(
    {
        'image/jpeg',
        'image/jpg',
        'image/pjpeg',
        'image/png',
        'image/gif',
        'image/webp',
        'image/bmp',
        'image/x-ms-bmp',
        'image/tiff',
    }
)
