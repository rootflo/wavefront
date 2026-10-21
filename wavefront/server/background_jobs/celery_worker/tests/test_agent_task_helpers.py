"""Unit tests for shared task helpers (no Redis / Celery broker)."""

import base64
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from db_repo_module.models.llm_inference_config import LlmInferenceConfig

from celery_worker.settings import STREAM_NAME
from celery_worker.tasks import helpers


def test_build_llm_config_none():
    assert helpers.build_llm_config(None) is None
    assert helpers.build_llm_config({}) is None


def test_build_llm_config_from_dict():
    with patch.object(
        helpers, 'LlmInferenceConfig', return_value=MagicMock(spec=LlmInferenceConfig)
    ) as ctor:
        cfg = helpers.build_llm_config({'model': 'gpt-4'})
        ctor.assert_called_once_with(model='gpt-4')
        assert cfg is ctor.return_value


def test_now_is_timezone_aware_iso():
    stamp = helpers.now_iso()
    parsed = datetime.fromisoformat(stamp)
    assert parsed.tzinfo is not None
    assert abs((datetime.now(timezone.utc) - parsed).total_seconds()) < 5


def test_reconstruct_inputs_passthrough_string():
    with patch.object(
        helpers, 'process_inference_inputs', return_value='processed'
    ) as process:
        result = helpers.reconstruct_inputs({'inputs': 'hello'}, MagicMock())
        process.assert_called_once_with('hello')
        assert result == 'processed'


def test_reconstruct_inputs_fetches_stored_document():
    cloud = MagicMock()
    cloud.read_file.return_value = b'pdf-bytes'
    payload = {
        'inputs': [
            {
                'stored': True,
                'bucket': 'app-bucket',
                'key': 'exec/file.pdf',
                'input_type': 'document',
                'mime_type': 'application/pdf',
                'file_name': 'file.pdf',
            }
        ]
    }

    with patch.object(
        helpers, 'process_inference_inputs', side_effect=lambda x: x
    ) as process:
        result = helpers.reconstruct_inputs(payload, cloud)

    cloud.read_file.assert_called_once_with('app-bucket', 'exec/file.pdf')
    rebuilt = process.call_args.args[0]
    assert rebuilt[0]['role'] == 'user'
    expected_b64 = base64.b64encode(b'pdf-bytes').decode('utf-8')
    assert rebuilt[0]['content']['document_base64'] == expected_b64
    assert rebuilt[0]['content']['mime_type'] == 'application/pdf'
    assert result == rebuilt


def test_reconstruct_inputs_fetches_stored_image():
    cloud = MagicMock()
    cloud.read_file.return_value = b'img-bytes'
    payload = {
        'inputs': [
            {
                'stored': True,
                'bucket': 'app-bucket',
                'key': 'exec/pic.png',
                'input_type': 'image',
                'mime_type': 'image/png',
            }
        ]
    }

    with patch.object(
        helpers, 'process_inference_inputs', side_effect=lambda x: x
    ) as process:
        helpers.reconstruct_inputs(payload, cloud)
        rebuilt = process.call_args.args[0]

    expected_b64 = base64.b64encode(b'img-bytes').decode('utf-8')
    assert rebuilt[0]['content']['image_base64'] == expected_b64
    assert 'document_base64' not in rebuilt[0]['content']


def test_reconstruct_inputs_keeps_non_stored_entries():
    cloud = MagicMock()
    payload = {
        'inputs': [
            {'role': 'user', 'content': 'plain'},
            {
                'stored': True,
                'bucket': 'b',
                'key': 'k',
                'input_type': 'document',
            },
        ]
    }
    cloud.read_file.return_value = b'data'

    with patch.object(
        helpers, 'process_inference_inputs', side_effect=lambda x: x
    ) as process:
        helpers.reconstruct_inputs(payload, cloud)
        rebuilt = process.call_args.args[0]

    assert rebuilt[0] == {'role': 'user', 'content': 'plain'}
    assert 'document_base64' in rebuilt[1]['content']
    cloud.read_file.assert_called_once_with('b', 'k')


def test_publish_xadds_to_stream_and_returns_message_id():
    cache = MagicMock()
    cache.namespace = 'floware'
    cache.xadd.return_value = '1-0'

    message_id = helpers.publish_result(
        cache,
        'exec-1',
        {'execution_id': 'exec-1', 'status': 'completed', 'error': ''},
    )

    assert message_id == '1-0'
    cache.xadd.assert_called_once_with(
        STREAM_NAME,
        {'execution_id': 'exec-1', 'status': 'completed', 'error': ''},
    )


def test_publish_reraises_after_xadd_failure():
    cache = MagicMock()
    cache.namespace = 'floware'
    cache.xadd.side_effect = ConnectionError('redis down')

    with pytest.raises(ConnectionError, match='redis down'):
        helpers.publish_result(cache, 'exec-1', {'status': 'failed'})


def test_build_history_shape():
    payload = {
        'execution_id': 'e1',
        'entity_type': 'agent',
        'entity_id': str(uuid4()),
        'inputs': 'hi',
        'variables': {'a': 1},
    }
    history = helpers.build_history(payload, result='out', exec_time=1.23456, trace=[])
    assert history['execution_id'] == 'e1'
    assert history['output'] == 'out'
    assert history['execution_time_seconds'] == 1.235
    assert history['variables'] == {'a': 1}
    assert history['trace'] == []


def test_build_history_defaults_empty_variables_and_trace():
    payload = {
        'execution_id': 'e1',
        'entity_type': 'agent',
        'entity_id': 'id',
        'inputs': 'hi',
    }
    history = helpers.build_history(payload, result='out', exec_time=0)
    assert history['variables'] == {}
    assert history['trace'] == []


def test_save_json_writes_encoded_payload():
    cloud = MagicMock()
    helpers.save_json(cloud, 'bucket', 'key.json', {'ok': True})
    cloud.save_small_file.assert_called_once()
    kwargs = cloud.save_small_file.call_args.kwargs
    assert kwargs['bucket_name'] == 'bucket'
    assert kwargs['key'] == 'key.json'
    assert kwargs['content_type'] == 'application/json'
    assert kwargs['file_content'] == b'{"ok": true}'
