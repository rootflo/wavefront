import cv2
import torchvision.transforms as transforms
from PIL import Image
import torch
import numpy as np
from pydantic import BaseModel, Field
from inference_app.utils.image_utils import decode_image_from_bytes


class PreprocessingStep(BaseModel):
    preprocess_filter: str
    values: list = Field(default_factory=list)


class ModelInferenceService:
    def __init__(self):
        self.device = torch.device('cpu')

    def preprocess_image(
        self,
        image_bytes,
        gaussian_blur_kernel,
        min_threshold,
        max_threshold,
        preprocessing_steps: list[PreprocessingStep],
    ):
        """Apply preprocessing steps based on provided flags."""
        processed_image = decode_image_from_bytes(image_bytes)

        # Define available preprocessing functions
        preprocessing_functions = {
            'gray': lambda img, values: cv2.cvtColor(img, cv2.COLOR_BGR2GRAY),
            'gaussian_blur': lambda img, values: cv2.GaussianBlur(
                img, (gaussian_blur_kernel, gaussian_blur_kernel), 0
            ),
            'canny': lambda img, values: cv2.cvtColor(
                cv2.Canny(img, min_threshold, max_threshold), cv2.COLOR_GRAY2RGB
            ),
            'kernel_sharpening': lambda img, values: cv2.filter2D(
                img, -1, np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
            ),
        }
        for step in preprocessing_steps:
            filter_name = step.preprocess_filter
            values = step.values
            if filter_name and filter_name in preprocessing_functions:
                processed_image = preprocessing_functions[filter_name](
                    processed_image, values
                )
            else:
                continue

        pil_image = Image.fromarray(processed_image)
        return pil_image

    def model_infer_score(
        self,
        model,
        image_bytes,
        resize_width,
        resize_height,
        normalize_mean,
        normalize_std,
        gaussian_blur_kernel,
        min_threshold,
        max_threshold,
        preprocessing_steps: list[PreprocessingStep],
    ):
        """
        Predict overlap score for a single image using the same preprocessing as training
        """
        # Define the same transform used during validation
        normalize_mean = [float(x) for x in normalize_mean.split(',')]
        normalize_std = [float(x) for x in normalize_std.split(',')]
        transform = transforms.Compose(
            [
                transforms.Resize((resize_width, resize_height)),
                transforms.ToTensor(),
                transforms.Normalize(mean=normalize_mean, std=normalize_std),
            ]
        )
        # Apply the same preprocessing as during training
        preprocessed_image = self.preprocess_image(
            image_bytes,
            gaussian_blur_kernel,
            min_threshold,
            max_threshold,
            preprocessing_steps,
        )

        # Apply transforms
        image_tensor = transform(preprocessed_image).unsqueeze(0).to(self.device)
        model.to(self.device)
        # Predict
        model.eval()
        with torch.no_grad():
            response = model(image_tensor).item()

        return response
