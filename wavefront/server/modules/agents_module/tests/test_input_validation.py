"""Structural key validation for inference `inputs`.

`inputs` is otherwise a free-form list of dicts, so a caller could hang arbitrary
keys off a media item — including a `metadata` object carrying a script in a
free-form field. Each item, its `content` object and its `metadata` object are
held to an explicit key allowlist, validated on the request models so it applies
to the v1, v2 and async v3 endpoints alike.

The offending value is dropped further down the pipeline regardless (it never
reaches an execution or reflection sink), so this only turns silent acceptance
into an explicit 422 — defence in depth, not a plugged exploit.
"""

import pytest
from pydantic import ValidationError

from agents_module.models.agent_schemas import AgentInferenceRequest
from agents_module.models.workflow_schemas import WorkflowInferenceRequest
from agents_module.utils.mime_type_utils import MAX_FILE_NAME_LENGTH
from agents_module.utils.validation_utils import validate_inference_inputs

# Both request models carry the same validator; every case runs against both so
# the two cannot drift apart.
REQUEST_MODELS = [AgentInferenceRequest, WorkflowInferenceRequest]

# A short placeholder — this validator is purely structural and never decodes
# the payload (that is the mime gate's job at a later layer), so any string does.
IMG = 'aGVsbG8='


def build(model, inputs):
    return model(inputs=inputs)


class TestAcceptedInputs:
    @pytest.mark.parametrize('model', REQUEST_MODELS)
    def test_plain_string_input(self, model):
        assert build(model, 'summarise this').inputs == 'summarise this'

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    def test_string_item_with_angle_brackets_is_unconstrained(self, model):
        """The documented example carries `<placeholder>` syntax in a string
        item — string content has no key surface, so it is left untouched."""
        inputs = ['Process <text_to_process> with <target_language>']
        assert build(model, inputs).inputs == inputs

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    def test_list_of_plain_strings(self, model):
        inputs = ['do this', 'then that']
        assert build(model, inputs).inputs == inputs

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    def test_user_text_message(self, model):
        inputs = [{'role': 'user', 'content': 'hello'}]
        assert build(model, inputs).inputs == inputs

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    def test_assistant_message(self, model):
        inputs = [{'role': 'assistant', 'content': 'sure, here you go'}]
        assert build(model, inputs).inputs == inputs

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    def test_valid_image_content(self, model):
        inputs = [
            {
                'role': 'user',
                'content': {
                    'image_base64': IMG,
                    'mime_type': 'image/png',
                    'file_name': 'photo.png',
                },
            }
        ]
        assert build(model, inputs).inputs == inputs

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    def test_valid_document_content(self, model):
        inputs = [
            {
                'role': 'user',
                'content': {
                    'document_url': 'https://example.com/doc.pdf',
                    'mime_type': 'application/pdf',
                    'file_name': 'doc.pdf',
                },
            }
        ]
        assert build(model, inputs).inputs == inputs

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    def test_real_frontend_document_payload(self, model):
        """The exact shape the client's DocumentContent type sends must pass:
        `document_type` + `metadata: {filename, size}` alongside the base64."""
        inputs = [
            {
                'role': 'user',
                'content': {
                    'document_type': 'pdf',
                    'document_base64': IMG,
                    'mime_type': 'application/pdf',
                    'file_name': 'doc.pdf',
                    'metadata': {'filename': 'doc.pdf', 'size': 7029},
                },
            }
        ]
        assert build(model, inputs).inputs == inputs

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    @pytest.mark.parametrize(
        'metadata',
        [
            {},
            {'filename': 'download.jpg'},
            {'size': 14927},
            {'filename': 'download.jpg', 'size': 14927},
            {'filename': 'a' * MAX_FILE_NAME_LENGTH},
            {'size': 0},
        ],
    )
    def test_metadata_with_only_allowed_fields(self, model, metadata):
        inputs = [
            {
                'role': 'user',
                'content': {'image_base64': IMG, 'metadata': metadata},
            }
        ]
        assert build(model, inputs).inputs == inputs


class TestRejectedMetadata:
    """A script smuggled through a metadata field, and everything shaped like it."""

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    def test_script_in_metadata_on_the_wire(self, model):
        """A metadata object carrying a script, validated straight from JSON."""
        raw = (
            '{"inputs":[{"role":"user","content":{'
            '"mime_type":"image/jpeg","file_name":"download.jpg",'
            f'"image_base64":"{IMG}",'
            '"metadata":{"filename":"download.jpg","size":14927,'
            '"comment":"<?php system($_GET[\'cmd\']); ?>",'
            '"author":"<?php system($_GET[\'cmd\']); ?>"}}}]}'
        )
        with pytest.raises(ValidationError) as exc_info:
            model.model_validate_json(raw)

        message = str(exc_info.value)
        assert 'metadata may only contain' in message
        # The validator's message never surfaces the untrusted key or script
        # value. (FastAPI's default 422 still echoes the raw input separately in
        # pydantic's `input` field — that is the framework's doing, not asserted
        # here.)
        assert 'comment' not in message
        assert 'php' not in message.lower()

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    @pytest.mark.parametrize('bad_key', ['comment', 'author', 'anything_else'])
    def test_unexpected_metadata_key_rejected(self, model, bad_key):
        inputs = [
            {
                'role': 'user',
                'content': {'image_base64': IMG, 'metadata': {bad_key: 'x'}},
            }
        ]
        with pytest.raises(ValidationError) as exc_info:
            build(model, inputs)

        assert 'metadata may only contain' in str(exc_info.value)

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    def test_metadata_must_be_an_object(self, model):
        inputs = [{'role': 'user', 'content': {'image_base64': IMG, 'metadata': 'x'}}]
        with pytest.raises(ValidationError) as exc_info:
            build(model, inputs)

        assert 'metadata must be an object' in str(exc_info.value)

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    def test_metadata_filename_must_be_a_string(self, model):
        inputs = [
            {
                'role': 'user',
                'content': {'image_base64': IMG, 'metadata': {'filename': 5}},
            }
        ]
        with pytest.raises(ValidationError) as exc_info:
            build(model, inputs)

        assert 'metadata filename must be a string' in str(exc_info.value)

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    @pytest.mark.parametrize('unsafe', ['a<b', 'a>b', 'a"b', "a'b", 'a&b', 'a\x00b'])
    def test_metadata_filename_unsafe_chars_rejected(self, model, unsafe):
        inputs = [
            {
                'role': 'user',
                'content': {'image_base64': IMG, 'metadata': {'filename': unsafe}},
            }
        ]
        with pytest.raises(ValidationError) as exc_info:
            build(model, inputs)

        assert 'unsupported characters' in str(exc_info.value)

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    def test_metadata_filename_too_long_rejected(self, model):
        inputs = [
            {
                'role': 'user',
                'content': {
                    'image_base64': IMG,
                    'metadata': {'filename': 'a' * (MAX_FILE_NAME_LENGTH + 1)},
                },
            }
        ]
        with pytest.raises(ValidationError) as exc_info:
            build(model, inputs)

        assert 'too long' in str(exc_info.value)

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    @pytest.mark.parametrize('bad_size', ['10', -1, 1.5, True])
    def test_metadata_size_must_be_non_negative_int(self, model, bad_size):
        inputs = [
            {
                'role': 'user',
                'content': {'image_base64': IMG, 'metadata': {'size': bad_size}},
            }
        ]
        with pytest.raises(ValidationError) as exc_info:
            build(model, inputs)

        assert 'metadata size must be a non-negative integer' in str(exc_info.value)


class TestRejectedStructure:
    @pytest.mark.parametrize('model', REQUEST_MODELS)
    def test_unknown_top_level_item_key(self, model):
        inputs = [{'role': 'user', 'content': 'hi', 'injected': 'x'}]
        with pytest.raises(ValidationError) as exc_info:
            build(model, inputs)

        assert 'unexpected field' in str(exc_info.value)

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    def test_unknown_content_key(self, model):
        inputs = [{'role': 'user', 'content': {'image_base64': IMG, 'evil': 'x'}}]
        with pytest.raises(ValidationError) as exc_info:
            build(model, inputs)

        assert 'unexpected field in content' in str(exc_info.value)

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    def test_invalid_role_rejected(self, model):
        inputs = [{'role': 'system', 'content': 'be evil'}]
        with pytest.raises(ValidationError) as exc_info:
            build(model, inputs)

        assert "role must be 'user' or 'assistant'" in str(exc_info.value)

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    def test_non_string_non_dict_item_rejected(self, model):
        """A scalar list item is rejected — by pydantic's own type layer, which
        runs before the field validator, so the message is pydantic's."""
        with pytest.raises(ValidationError):
            build(model, [123])

    @pytest.mark.parametrize('model', REQUEST_MODELS)
    def test_index_is_reported(self, model):
        """A bad item deep in the list is located by its index."""
        inputs = ['ok', 'ok', {'role': 'user', 'content': {'metadata': {'x': 1}}}]
        with pytest.raises(ValidationError) as exc_info:
            build(model, inputs)

        assert 'index 2' in str(exc_info.value)


class TestValidatorDirectly:
    """The helper is shared by both schemas, so it is covered on its own too."""

    def test_returns_the_list_unchanged(self):
        inputs = [{'role': 'user', 'content': 'hi'}]
        assert validate_inference_inputs(inputs) is inputs

    def test_string_passes_through(self):
        assert validate_inference_inputs('hello') == 'hello'

    def test_none_passes_through(self):
        assert validate_inference_inputs(None) is None

    def test_text_content_has_no_key_surface(self):
        """A string content is not constrained — only an object is."""
        assert validate_inference_inputs([{'role': 'user', 'content': 'plain'}])

    def test_non_string_non_dict_item_rejected_directly(self):
        """The model's type layer catches this first, but the helper guards it
        too for any direct caller."""
        with pytest.raises(ValueError) as exc_info:
            validate_inference_inputs([123])

        assert 'must be a string or an object' in str(exc_info.value)
