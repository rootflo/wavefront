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
# allow_patterns (hf, optional) → only these files are downloaded
# post_process (optional)       → name of a step run after download (and on
#                                 re-runs, so an interrupted one is finished)
# optional (optional)           → the inference app starts without it
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
    {
        # Text embeddings (dense + sparse). Skips the repo's ONNX export,
        # ColBERT head and images (~2GB more).
        'local_name': 'bge-m3-hf',
        'source': 'hf',
        'repo_id': 'BAAI/bge-m3',
        'env_var': 'BGE_M3_MODEL_URI',
        'allow_patterns': [
            'config.json',
            'pytorch_model.bin',
            'sparse_linear.pt',
            'sentencepiece.bpe.model',
            'special_tokens_map.json',
            'tokenizer.json',
            'tokenizer_config.json',
        ],
        'post_process': 'convert_bge_m3_to_safetensors',
        'optional': True,
    },
]

SCRIPT_DIR = Path(__file__).resolve().parent
LOCAL_CACHE = SCRIPT_DIR / '.mcache'


# ── Download ──────────────────────────────────────────────────────────────────


def download_models(hf_token: str) -> None:
    LOCAL_CACHE.mkdir(exist_ok=True)
    for model in MODELS:
        dest = LOCAL_CACHE / model['local_name']
        if _has_model_files(dest):
            print(f"[skip] {model['local_name']} already downloaded.")
            _post_process(model, dest)
            continue

        if model['source'] == 'hf':
            print(f"[download:hf] {model['repo_id']} → {dest}")
            snapshot_download(
                repo_id=model['repo_id'],
                local_dir=str(dest),
                token=hf_token,
                allow_patterns=model.get('allow_patterns'),
            )

        elif model['source'] == 'timm':
            import timm
            from safetensors.torch import save_file

            print(f"[download:timm] {model['repo_id']} → {dest}")
            dest.mkdir(parents=True, exist_ok=True)
            m = timm.create_model(model['repo_id'], pretrained=True)
            save_file(m.state_dict(), str(dest / 'model.safetensors'))

        _post_process(model, dest)
        print(f"[done] {model['local_name']}")


def _has_model_files(dest: Path) -> bool:
    """True once the folder holds model files. Ignores hidden entries such as
    the .cache/ huggingface_hub creates up front, which a failed download
    (e.g. a gated repo without a token) leaves behind on its own."""
    return dest.is_dir() and any(not p.name.startswith('.') for p in dest.iterdir())


def _post_process(model: dict, dest: Path) -> None:
    step = model.get('post_process')
    if step:
        POST_PROCESS_STEPS[step](dest)


def convert_bge_m3_to_safetensors(model_dir: Path) -> None:
    """Convert BGE-M3's pickled weights to safetensors and drop the pickles.

    BAAI/bge-m3 ships only pytorch_model.bin. transformers refuses to load
    .bin checkpoints on torch < 2.6 (CVE-2025-32434), and the inference app
    loads safetensors only, so nothing in a synced model directory is ever
    unpickled. Converting here uses torch.load(weights_only=True), which only
    reconstructs tensors. Idempotent: does nothing once converted.
    """
    import torch
    from safetensors.torch import save_file

    conversions = [
        ('pytorch_model.bin', 'model.safetensors'),
        ('sparse_linear.pt', 'sparse_linear.safetensors'),
    ]
    for source_name, target_name in conversions:
        source, target = model_dir / source_name, model_dir / target_name
        if target.exists():
            if source.exists():
                source.unlink()
            continue
        if not source.exists():
            raise FileNotFoundError(f'{source} is missing; re-run the download')
        print(f'[convert] {source_name} → {target_name}')
        state_dict = torch.load(source, map_location='cpu', weights_only=True)
        # clone: safetensors refuses tensors that share storage
        tensors = {
            name: tensor.contiguous().clone() for name, tensor in state_dict.items()
        }
        # write-then-rename so an interrupted run never leaves a partial file
        partial = target.with_suffix('.partial')
        save_file(tensors, str(partial), metadata={'format': 'pt'})
        partial.rename(target)
        source.unlink()


POST_PROCESS_STEPS = {
    'convert_bge_m3_to_safetensors': convert_bge_m3_to_safetensors,
}


def _print_env_vars() -> None:
    print('\nDone.\nSet these env vars for the inference app:')
    for model in MODELS:
        note = '  # optional' if model.get('optional') else ''
        print(f"  {model['env_var']}={LOCAL_CACHE / model['local_name']}{note}")


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
