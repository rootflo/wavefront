import cv2
from common_module.log.logger import logger
from inference_app.utils.image_utils import decode_image_from_bytes


class ImageClarityService:
    def __init__(self):
        pass

    def laplacian_detection(self, image_bytes, max_expected_variance):
        # Decode image from bytes array
        logger.info(
            f'Successfully decoded Base64 string. Data length: {len(image_bytes)} bytes.'
        )
        images = decode_image_from_bytes(image_bytes)
        images = cv2.resize(images, (256, 256), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(images, cv2.COLOR_BGR2GRAY)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        variance = laplacian.var()
        clamped_variance = min(variance, int(max_expected_variance))
        score = (clamped_variance / int(max_expected_variance)) * 100
        return int(score)
