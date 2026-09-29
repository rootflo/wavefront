#!/usr/bin/env python3
"""
Download models from HuggingFace into the local cache (scripts/.mcache).

The inference app uses local model paths directly, so point the *_MODEL_URI
env vars at the printed directories.

Usage:
  python download_models.py --hf-token hf_xxx
"""

import argparse
import os
from pathlib import Path

from huggingface_hub import snapshot_download

# ── Model registry ────────────────────────────────────────────────────────────
# source: "hf"   → downloaded via huggingface_hub.snapshot_download
# source: "timm" → downloaded via timm.create_model (weights saved as safetensors)
MODELS = [
    {
        'local_name': 'clip-vit-base-patch32-hf',
        'source': 'hf',
        'repo_id': 'openai/clip-vit-base-patch32',
        'env_var': 'CLIP_VIT_BASE_PATCH32_MODEL_URI',
    },
    {
        'local_name': 'dinov3-vitl16-hf',
        'source': 'hf',
        'repo_id': 'facebook/dinov3-vitl16-pretrain-lvd1689m',
        'env_var': 'DINOV3_VITL16_HF_MODEL_URI',
    },
]

SCRIPT_DIR = Path(__file__).resolve().parent
LOCAL_CACHE = SCRIPT_DIR / '.mcache'


# ── Download ──────────────────────────────────────────────────────────────────


def download_models(hf_token: str) -> None:
    LOCAL_CACHE.mkdir(exist_ok=True)
    for model in MODELS:
        dest = LOCAL_CACHE / model['local_name']
        if dest.exists() and any(dest.iterdir()):
            print(f"[skip] {model['local_name']} already downloaded.")
            continue

        if model['source'] == 'hf':
            print(f"[download:hf] {model['repo_id']} → {dest}")
            snapshot_download(
                repo_id=model['repo_id'],
                local_dir=str(dest),
                token=hf_token,
            )

        elif model['source'] == 'timm':
            import timm
            from safetensors.torch import save_file

            print(f"[download:timm] {model['repo_id']} → {dest}")
            dest.mkdir(parents=True, exist_ok=True)
            m = timm.create_model(model['repo_id'], pretrained=True)
            save_file(m.state_dict(), str(dest / 'model.safetensors'))

        print(f"[done] {model['local_name']}")


def _print_env_vars() -> None:
    print('\nDone.\nSet these env vars for the inference app:')
    for model in MODELS:
        print(f"  {model['env_var']}={LOCAL_CACHE / model['local_name']}")


# ── CLI ───────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description='Download HF models to the local cache.'
    )
    parser.add_argument(
        '--hf-token', default=os.environ.get('HF_TOKEN', ''), help='HuggingFace token'
    )
    args = parser.parse_args()

    download_models(args.hf_token)
    _print_env_vars()


if __name__ == '__main__':
    main()
