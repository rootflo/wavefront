import os

CLOUD_PROVIDER = os.getenv('CLOUD_PROVIDER', '')

# HF model: openai/clip-vit-base-patch32
CLIP_VIT_BASE_PATCH32_MODEL_URI = os.getenv('CLIP_VIT_BASE_PATCH32_MODEL_URI', '')

# HF model: facebook/dinov3-vitl16-pretrain-lvd1689m
DINOV3_VITL16_HF_MODEL_URI = os.getenv('DINOV3_VITL16_HF_MODEL_URI', '')

MODEL_CACHE_DIR = os.getenv('MODEL_CACHE_DIR', '/tmp/model-cache')

# Largest batch /v1/query/embeddings/batch accepts. Inference runs on CPU, where
# DINOv3 ViT-L takes ~1-2s per image, so 8 keeps a full batch well inside the
# ingestion client's timeout. Keep IMAGE_EMBEDDING_BATCH_SIZE in rag_ingestion
# at or below this.
MAX_EMBEDDING_BATCH_SIZE = int(os.getenv('MAX_EMBEDDING_BATCH_SIZE', '8'))

# Limits on the embedding endpoints, applied across all callers (each batch
# call counts as one request). Set either to 0 to disable that window.
RATE_LIMIT_REQUESTS_PER_SECOND = int(os.getenv('RATE_LIMIT_REQUESTS_PER_SECOND', '4'))
RATE_LIMIT_REQUESTS_PER_MINUTE = int(os.getenv('RATE_LIMIT_REQUESTS_PER_MINUTE', '240'))
