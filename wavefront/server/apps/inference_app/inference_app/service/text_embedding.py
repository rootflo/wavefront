import threading
from pathlib import Path
from typing import Any, Dict, List, Union

import torch
from common_module.log.logger import logger
from safetensors.torch import load_file
from transformers import AutoModel, AutoTokenizer

SPARSE_LINEAR_FILE = 'sparse_linear.safetensors'


class TextEmbedding:
    """BGE-M3 dense and sparse (lexical) text embeddings.

    Loads a model directory prepared by scripts/download_models.py: the
    XLM-RoBERTa encoder from model.safetensors plus BGE-M3's sparse head from
    sparse_linear.safetensors. Only safetensors are read, so nothing in a
    synced model directory is unpickled or executed.

    - dense: the [CLS] hidden state, L2-normalized (1024 dims for BGE-M3).
    - sparse: relu(sparse_linear(hidden state)) per token, keeping the highest
      weight per token id and dropping special tokens, as BGE-M3's reference
      implementation (FlagEmbedding) computes its lexical weights. Returned as
      token-id indices and weights over a `sparse_dim`-sized vocabulary.
    """

    def __init__(self, model_dir: Union[str, Path], max_length: int = 512):
        path = Path(model_dir)
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.max_length = max_length

        logger.info('Loading BGE-M3 text embedding model from %s', path)
        self.tokenizer = AutoTokenizer.from_pretrained(path)
        self.model = AutoModel.from_pretrained(path, use_safetensors=True)
        self.model.to(self.device).eval()

        sparse_path = path / SPARSE_LINEAR_FILE
        if not sparse_path.is_file():
            raise FileNotFoundError(
                f'{sparse_path} not found. Prepare the model directory with '
                'scripts/download_models.py, which converts sparse_linear.pt.'
            )
        self.sparse_linear = torch.nn.Linear(self.model.config.hidden_size, 1)
        self.sparse_linear.load_state_dict(load_file(str(sparse_path)))
        self.sparse_linear.to(self.device).eval()

        self.dense_dim = self.model.config.hidden_size
        self.sparse_dim = len(self.tokenizer)
        self._excluded_token_ids = {
            token_id
            for token_id in (
                self.tokenizer.cls_token_id,
                self.tokenizer.eos_token_id,
                self.tokenizer.pad_token_id,
                self.tokenizer.unk_token_id,
            )
            if token_id is not None
        }
        # Requests run on FastAPI's threadpool; one forward pass at a time.
        self._model_lock = threading.Lock()
        logger.info(
            'BGE-M3 loaded on %s (dense_dim=%d, sparse_dim=%d, max_length=%d)',
            self.device,
            self.dense_dim,
            self.sparse_dim,
            self.max_length,
        )

    @torch.inference_mode()
    def embed(
        self,
        texts: List[str],
        return_dense: bool = True,
        return_sparse: bool = True,
    ) -> List[Dict[str, Any]]:
        """One result per text, in order, with 'dense' and/or 'sparse'."""
        inputs = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors='pt',
        )
        inputs = {name: tensor.to(self.device) for name, tensor in inputs.items()}

        with self._model_lock:
            hidden = self.model(**inputs).last_hidden_state
            token_weights = (
                torch.relu(self.sparse_linear(hidden)).squeeze(-1)
                if return_sparse
                else None
            )

        results: List[Dict[str, Any]] = [{} for _ in texts]
        if return_dense:
            dense = torch.nn.functional.normalize(hidden[:, 0], dim=-1)
            for result, vector in zip(results, dense.cpu().tolist()):
                result['dense'] = vector
        if return_sparse:
            input_ids = inputs['input_ids'].cpu().tolist()
            mask = inputs['attention_mask'].cpu().tolist()
            weights = token_weights.float().cpu().tolist()
            for result, ids, keep, row in zip(results, input_ids, mask, weights):
                result['sparse'] = self._lexical_weights(ids, keep, row)
        return results

    def _lexical_weights(
        self, input_ids: List[int], attention_mask: List[int], weights: List[float]
    ) -> Dict[str, List]:
        best: Dict[int, float] = {}
        for token_id, keep, weight in zip(input_ids, attention_mask, weights):
            if not keep or token_id in self._excluded_token_ids or weight <= 0:
                continue
            if weight > best.get(token_id, 0.0):
                best[token_id] = weight
        indices = sorted(best)
        return {'indices': indices, 'values': [best[i] for i in indices]}


# Re-exported: these used to live here, and don't need torch.
from inference_app.service.text_embedding_provider import (  # noqa: E402,F401
    TextEmbeddingProvider,
    TextEmbeddingUnavailable,
)
