import cv2
import numpy as np
import io
from PIL import Image
from common_module.log.logger import logger


def decode_image_from_bytes(image_bytes: bytes):
    """
    Decodes an image from bytes using OpenCV, with a Pillow fallback.

    Args:
        image_bytes: The image data as bytes.

    Returns:
        The decoded image as a NumPy array (OpenCV format).

    Raises:
        ValueError: If the image could not be decoded.
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    logger.info(f'Image decoding output is printed here: {image is not None}.')
    if image is None:
        try:
            # Fallback to Pillow
            img_pil = Image.open(io.BytesIO(image_bytes))
            # Convert PIL Image to an OpenCV compatible format
            image = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
            logger.info(f'Pillow fallback successful. {image is not None}.')
        except Exception as pil_e:
            logger.error(f'Pillow (PIL) fallback also failed: {pil_e}')
            raise ValueError('Could not decode image from bytes')
    return image
