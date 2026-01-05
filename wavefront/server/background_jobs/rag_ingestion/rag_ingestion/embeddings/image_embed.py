import torch
from transformers import CLIPProcessor, CLIPModel, AutoImageProcessor, AutoModel
from PIL import Image
import io
from rag_ingestion.models.knowledge_base_embeddings import KnowledgeBaseEmbeddingObject


class ImageEmbedding:
    def __init__(self):
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f'Initializing models on device: {self.device}')

        # CLIP Model (Fixed: Added .to(self.device))
        self.clip_model_name = 'openai/clip-vit-base-patch32'
        self.model = (
            CLIPModel.from_pretrained(self.clip_model_name).to(self.device).eval()
        )
        self.processor = CLIPProcessor.from_pretrained(self.clip_model_name)

        # DINO Model (No change needed for device_map="auto")
        self.dino_model_name = 'facebook/dinov3-vitl16-pretrain-lvd1689m'
        self.dino_processor = AutoImageProcessor.from_pretrained(self.dino_model_name)
        self.dino_model = AutoModel.from_pretrained(
            self.dino_model_name, device_map='auto', trust_remote_code=True
        ).eval()

    def embed_image(self, file_content: bytes) -> KnowledgeBaseEmbeddingObject:
        image = Image.open(io.BytesIO(file_content))
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # CLIP Inputs (Fixed: Added .to(self.device))
        inputs = self.processor(images=image, return_tensors='pt').to(self.device)

        # --- CLIP EMBEDDING ---
        with torch.no_grad():
            image_features = self.model.get_image_features(**inputs)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            embedding = image_features.squeeze().cpu().numpy().tolist()

        # --- DINO EMBEDDING CALL ---
        dino_embedding = self.embed_image_dino(file_content)

        # Pass the DINO embedding to the correct field
        return KnowledgeBaseEmbeddingObject(
            embedding_vector=embedding,
            embedding_vector_1=dino_embedding,
            chunk_text='image data',
            chunk_index='chunk_0',
        )

    @torch.inference_mode()
    def embed_image_dino(self, file_content: bytes) -> list:
        image = Image.open(io.BytesIO(file_content))
        if image.mode != 'RGB':
            image = image.convert('RGB')

        inputs = self.dino_processor(images=image, return_tensors='pt')

        target_device = self.dino_model.device
        # Move inputs to the DINO model's device
        inputs = {k: v.to(target_device) for k, v in inputs.items()}

        outputs = self.dino_model(**inputs)

        image_features = outputs.last_hidden_state[:, 0]

        image_features = image_features / image_features.norm(dim=-1, keepdim=True)
        embedding = image_features.squeeze().cpu().numpy().tolist()

        return embedding
