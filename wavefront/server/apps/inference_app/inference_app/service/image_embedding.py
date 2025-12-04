import torch
from transformers import CLIPProcessor, CLIPModel, AutoImageProcessor, AutoModel
from PIL import Image
import io
from typing import List, Dict, Any
from common_module.log.logger import logger


class ImageEmbedding:
    CLIP_MODEL_NAME = 'openai/clip-vit-base-patch32'
    DINO_MODEL_NAME = 'facebook/dinov3-vitl16-pretrain-lvd1689m'

    def __init__(self):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        logger.info(f'Using device: {self.device}')

        self.clip_processor = CLIPProcessor.from_pretrained(self.CLIP_MODEL_NAME)
        self.clip_model = CLIPModel.from_pretrained(self.CLIP_MODEL_NAME).to(
            self.device
        )
        self.clip_model.eval()

        self.dino_processor = AutoImageProcessor.from_pretrained(self.DINO_MODEL_NAME)
        self.dino_model = AutoModel.from_pretrained(
            self.DINO_MODEL_NAME, trust_remote_code=True
        ).to(self.device)
        self.dino_model.eval()

        self.embedders: Dict[str, Dict[str, Any]] = {
            'clip': {
                'processor': self.clip_processor,
                'model': self.clip_model,
                'extractor': self._extract_clip_features,
            },
            'dino': {
                'processor': self.dino_processor,
                'model': self.dino_model,
                'extractor': self._extract_dino_features,
            },
        }

    def _extract_clip_features(self, inputs: Dict[str, Any]) -> torch.Tensor:
        return self.clip_model.get_image_features(**inputs)

    def _extract_dino_features(self, inputs: Dict[str, Any]) -> torch.Tensor:
        outputs = self.dino_model(**inputs)
        return outputs.last_hidden_state[:, 0]

    @torch.inference_mode()
    def query_embed(self, image_content: bytes) -> List[Dict[str, List[float]]]:
        try:
            image = Image.open(io.BytesIO(image_content)).convert('RGB')
        except Exception as e:
            print(f'Error opening image: {e}')
            return []

        results = []

        for name, embedder in self.embedders.items():
            inputs = embedder['processor'](images=image, return_tensors='pt')

            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            image_features = embedder['extractor'](inputs)

            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            embedding = image_features.squeeze().cpu().numpy().tolist()

            results.append({name: embedding})

        return results
