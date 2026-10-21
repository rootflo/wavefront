"""
Tests for BGE-M3 text embeddings: the download script's safetensors
conversion, TextEmbedding's dense and sparse outputs, and the optional,
background-loading TextEmbeddingProvider.

A tiny randomly initialised XLM-RoBERTa stands in for BGE-M3, saved the way
the HF repo ships it (pytorch_model.bin + sparse_linear.pt), so no download
happens.
"""

import math
import threading
import time
from pathlib import Path

import pytest

torch = pytest.importorskip('torch')

from tokenizers import Tokenizer  # noqa: E402
from tokenizers.models import WordLevel  # noqa: E402
from tokenizers.pre_tokenizers import Whitespace  # noqa: E402
from tokenizers.processors import TemplateProcessing  # noqa: E402
from transformers import (  # noqa: E402
    PreTrainedTokenizerFast,
    XLMRobertaConfig,
    XLMRobertaModel,
)

from inference_app.scripts.download_models import (  # noqa: E402
    MODELS,
    convert_bge_m3_to_safetensors,
)
from inference_app.service.text_embedding import TextEmbedding  # noqa: E402
from inference_app.service.text_embedding_provider import (  # noqa: E402
    TextEmbeddingProvider,
    TextEmbeddingUnavailable,
)

SPECIAL = ['<s>', '<pad>', '</s>', '<unk>']
WORDS = ['the', 'cat', 'sat', 'on', 'mat', 'dog', 'ran']
HIDDEN = 32


def save_tokenizer(path: Path):
    vocab = {token: i for i, token in enumerate(SPECIAL + WORDS)}
    backend = Tokenizer(WordLevel(vocab, unk_token='<unk>'))
    backend.pre_tokenizer = Whitespace()
    backend.post_processor = TemplateProcessing(
        single='<s> $A </s>',
        special_tokens=[('<s>', vocab['<s>']), ('</s>', vocab['</s>'])],
    )
    PreTrainedTokenizerFast(
        tokenizer_object=backend,
        bos_token='<s>',
        cls_token='<s>',
        eos_token='</s>',
        sep_token='</s>',
        pad_token='<pad>',
        unk_token='<unk>',
    ).save_pretrained(path)


def save_bge_m3_like_repo(path: Path):
    """What snapshot_download leaves: pickled weights, no safetensors."""
    torch.manual_seed(0)
    config = XLMRobertaConfig(
        vocab_size=len(SPECIAL) + len(WORDS),
        hidden_size=HIDDEN,
        num_hidden_layers=2,
        num_attention_heads=2,
        intermediate_size=64,
        max_position_embeddings=64,
        pad_token_id=1,
    )
    XLMRobertaModel(config, add_pooling_layer=False).save_pretrained(
        path, safe_serialization=False
    )
    sparse_linear = torch.nn.Linear(HIDDEN, 1)
    torch.nn.init.normal_(sparse_linear.weight, std=1.0)
    torch.nn.init.constant_(sparse_linear.bias, 0.5)  # most weights > 0
    torch.save(sparse_linear.state_dict(), path / 'sparse_linear.pt')
    save_tokenizer(path)


@pytest.fixture
def bge_dir(tmp_path) -> Path:
    save_bge_m3_like_repo(tmp_path)
    convert_bge_m3_to_safetensors(tmp_path)
    return tmp_path


@pytest.fixture
def model(bge_dir) -> TextEmbedding:
    return TextEmbedding(bge_dir, max_length=32)


class TestDownloadScript:
    def test_bge_m3_is_registered_as_optional_with_filtered_files(self):
        [entry] = [m for m in MODELS if m['repo_id'] == 'BAAI/bge-m3']

        assert entry['env_var'] == 'BGE_M3_MODEL_URI'
        assert entry['optional'] is True
        assert entry['post_process'] == 'convert_bge_m3_to_safetensors'
        assert 'pytorch_model.bin' in entry['allow_patterns']
        assert not any('onnx' in pattern for pattern in entry['allow_patterns'])

    def test_conversion_replaces_pickles_with_safetensors(self, tmp_path):
        save_bge_m3_like_repo(tmp_path)

        convert_bge_m3_to_safetensors(tmp_path)

        assert (tmp_path / 'model.safetensors').is_file()
        assert (tmp_path / 'sparse_linear.safetensors').is_file()
        assert not (tmp_path / 'pytorch_model.bin').exists()
        assert not (tmp_path / 'sparse_linear.pt').exists()
        assert not list(tmp_path.glob('*.partial'))

    def test_conversion_is_idempotent(self, bge_dir):
        before = (bge_dir / 'model.safetensors').stat().st_mtime_ns

        convert_bge_m3_to_safetensors(bge_dir)

        assert (bge_dir / 'model.safetensors').stat().st_mtime_ns == before

    def test_conversion_fails_clearly_when_weights_are_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError, match='pytorch_model.bin'):
            convert_bge_m3_to_safetensors(tmp_path)


class TestTextEmbedding:
    def test_dense_vectors_are_normalized_cls_embeddings(self, model):
        [a, b] = model.embed(['the cat sat', 'the dog ran'], return_sparse=False)

        assert set(a) == {'dense'}
        assert len(a['dense']) == HIDDEN == model.dense_dim
        assert math.isclose(sum(v * v for v in a['dense']), 1.0, rel_tol=1e-4)
        assert a['dense'] != b['dense']

    def test_sparse_weights_follow_bge_m3(self, model):
        text = 'the cat sat on the mat'
        [result] = model.embed([text], return_dense=False)
        sparse = result['sparse']

        # Recompute independently: relu(sparse_linear(hidden)), max per token
        # id, special tokens dropped.
        inputs = model.tokenizer([text], return_tensors='pt')
        with torch.no_grad():
            hidden = model.model(**inputs).last_hidden_state
            weights = torch.relu(model.sparse_linear(hidden)).squeeze(-1)[0]
        expected = {}
        for token_id, weight in zip(inputs['input_ids'][0].tolist(), weights.tolist()):
            if token_id in model._excluded_token_ids or weight <= 0:
                continue
            expected[token_id] = max(weight, expected.get(token_id, 0.0))

        assert sparse['indices'] == sorted(expected)
        assert sparse['values'] == pytest.approx(
            [expected[i] for i in sparse['indices']]
        )
        assert model.sparse_dim == len(SPECIAL) + len(WORDS)

    def test_special_and_padding_tokens_never_appear_in_sparse(self, model):
        # the short text is padded to the long one's length
        results = model.embed(['cat', 'the cat sat on the mat'], return_dense=False)

        special_ids = set(model.tokenizer.convert_tokens_to_ids(SPECIAL))
        for result in results:
            assert not special_ids & set(result['sparse']['indices'])
            assert all(value > 0 for value in result['sparse']['values'])

    def test_batch_results_match_single_results(self, model):
        texts = ['the cat sat', 'dog ran on the mat']

        batch = model.embed(texts)
        singles = [model.embed([text])[0] for text in texts]

        for got, want in zip(batch, singles):
            assert got['dense'] == pytest.approx(want['dense'], abs=1e-5)
            assert got['sparse']['indices'] == want['sparse']['indices']
            assert got['sparse']['values'] == pytest.approx(
                want['sparse']['values'], abs=1e-5
            )

    def test_long_texts_are_truncated_to_max_length(self, bge_dir):
        model = TextEmbedding(bge_dir, max_length=8)

        [result] = model.embed([' '.join(WORDS * 10)])

        assert len(result['dense']) == HIDDEN

    def test_lexical_weights_keep_max_per_token(self, model):
        cls, eos, pad = (
            model.tokenizer.convert_tokens_to_ids(t) for t in ('<s>', '</s>', '<pad>')
        )
        cat, mat = (model.tokenizer.convert_tokens_to_ids(t) for t in ('cat', 'mat'))

        weights = model._lexical_weights(
            [cls, cat, mat, cat, eos, pad],
            [1, 1, 1, 1, 1, 0],
            [0.9, 0.2, -0.1, 0.7, 0.8, 0.6],
        )

        assert weights == {'indices': [cat], 'values': [0.7]}

    def test_missing_sparse_head_fails_with_guidance(self, bge_dir):
        (bge_dir / 'sparse_linear.safetensors').unlink()

        with pytest.raises(FileNotFoundError, match='download_models.py'):
            TextEmbedding(bge_dir)

    def test_unconverted_pickled_weights_are_not_loaded(self, tmp_path):
        save_bge_m3_like_repo(tmp_path)  # pytorch_model.bin only

        with pytest.raises(OSError):
            TextEmbedding(tmp_path)


class TestTextEmbeddingProvider:
    def test_disabled_until_loading_starts(self):
        provider = TextEmbeddingProvider()

        assert provider.status == 'disabled'
        with pytest.raises(TextEmbeddingUnavailable, match='BGE_M3_MODEL_URI'):
            provider.get()

    def test_failed_load_is_recorded_not_raised(self):
        provider = TextEmbeddingProvider()

        def broken_loader():
            raise ValueError('model dir missing')

        provider.load(broken_loader)

        assert provider.status == 'failed'
        with pytest.raises(TextEmbeddingUnavailable, match='model dir missing'):
            provider.get()

    def test_background_load_does_not_block(self):
        provider = TextEmbeddingProvider()
        release = threading.Event()
        sentinel = object()

        def slow_loader():
            release.wait(timeout=5)
            return sentinel

        started = time.monotonic()
        thread = provider.start_loading(slow_loader)

        assert time.monotonic() - started < 0.5
        assert thread.daemon
        with pytest.raises(TextEmbeddingUnavailable, match='still loading'):
            provider.get()

        release.set()
        thread.join(timeout=5)
        assert provider.status == 'ready'
        assert provider.get() is sentinel
