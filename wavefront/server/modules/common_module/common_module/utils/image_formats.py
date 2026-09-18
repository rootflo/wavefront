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
