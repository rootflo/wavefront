import torch
from transformers import CLIPProcessor, CLIPModel, AutoImageProcessor, AutoModel
from PIL import Image
import io
from typing import List, Dict, Any
from common_module.log.logger import logger

CLIP_MODEL_NAME = 'openai/clip-vit-base-patch32'
DINO_MODEL_NAME = 'facebook/dinov3-vitl16-pretrain-lvd1689m'


class ImageEmbedding:
    def __init__(self):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        logger.info(f'Using device: {self.device}')

        self.clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME)
        self.clip_model = CLIPModel.from_pretrained(CLIP_MODEL_NAME).to(
            self.device
        )
        self.clip_model.eval()

        self.dino_processor = AutoImageProcessor.from_pretrained(DINO_MODEL_NAME)
        self.dino_model = AutoModel.from_pretrained(
            DINO_MODEL_NAME, trust_remote_code=True
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

    @torch.inference_mode()
    def query_embed_batch(
        self, image_batch: list[bytes]
    ) -> List[Dict[str, List[List[float]]]]:
        """
        GPU batch embedding.

        Returns:
          [
            {"clip": [embedding_for_image_0, ..., embedding_for_image_N]},
            {"dino": [embedding_for_image_0, ..., embedding_for_image_N]},
          ]
        """
        if not image_batch:
            return []

        # Decode bytes -> PIL images on CPU.
        # The actual model forward pass (processor->tensor + model) is batched on GPU.
        images: List[Image.Image] = []
        for idx, image_content in enumerate(image_batch):
            try:
                images.append(Image.open(io.BytesIO(image_content)).convert('RGB'))
            except Exception as e:
                logger.error(
                    f'Error opening image at index={idx}: {e}',
                    exc_info=True,
                )
                raise ValueError(
                    f'Failed to decode image at index {idx}: {e}'
                ) from e

        results: List[Dict[str, List[List[float]]]] = []

        for name, embedder in self.embedders.items():
            inputs = embedder['processor'](images=images, return_tensors='pt')
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Batched forward pass.
            image_features = embedder['extractor'](inputs)  # (batch, dim)

            # L2-normalize per-vector.
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)

            embeddings = image_features.cpu().numpy().tolist()  # batch x dim
            results.append({name: embeddings})

        return results
