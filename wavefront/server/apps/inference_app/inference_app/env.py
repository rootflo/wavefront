import os

CLOUD_PROVIDER = os.getenv("CLOUD_PROVIDER", "")

# HF model: openai/clip-vit-base-patch32
CLIP_VIT_BASE_PATCH32_MODEL_URI = os.getenv("CLIP_VIT_BASE_PATCH32_MODEL_URI", "")

# HF model: facebook/dinov3-vitl16-pretrain-lvd1689m
DINOV3_VITL16_HF_MODEL_URI = os.getenv("DINOV3_VITL16_HF_MODEL_URI", "")

MODEL_CACHE_DIR = os.getenv("MODEL_CACHE_DIR", "/tmp/model-cache")
