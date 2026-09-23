"""Tests for the function-node adapter's parameter extraction and dispatch.

The adapter bridges flo_ai's node signature (``inputs``/``variables``) and the
plain signatures of registry functions. Two behaviours matter most here:

- every message selected by ``input_filter`` is read, not only the last one, and
  the payloads stay attributable to the node that produced them
- functions declaring ``**kwargs`` (the message processor, whose inputs are
  defined per-processor and cannot be named in the signature) receive the
  dynamic parameters, while fixed-signature functions are unaffected
"""

import pytest

from flo_ai.models import DocumentMessageContent, TextMessageContent, UserMessage

from tools_module.registry.function_node_adapter import (
    create_function_node_adapter,
    extract_function_params,
)


def message(content: str, node: str | None = None) -> UserMessage:
    metadata = {'node': node} if node else None
    return UserMessage(content=content, metadata=metadata)


class TestSingleInputIsUnchanged:
    """A one-message node must produce exactly the params it always did."""

    def test_upstream_json_becomes_params(self):
        params = extract_function_params([message('{"table_name": "people"}')])

        assert params['table_name'] == 'people'

    def test_prefilled_kwargs_win_over_input(self):
        params = extract_function_params(
            [message('{"datasource_id": "from-input"}')],
            None,
            datasource_id='from-prefill',
        )

        assert params['datasource_id'] == 'from-prefill'

    def test_variables_win_over_input(self):
        params = extract_function_params(
            [message('{"tone": "casual"}')], {'tone': 'formal'}
        )

        assert params['tone'] == 'formal'

    def test_non_json_last_message_still_raises(self):
        with pytest.raises(ValueError, match='Invalid JSON'):
            extract_function_params([message('not json at all')])

    def test_no_inputs_is_tolerated(self):
        params = extract_function_params(None, {'a': 1})

        assert params == {'a': 1}


class TestEveryInputIsRead:
    def test_all_messages_merge_into_params(self):
        params = extract_function_params([message('{"a": 1}'), message('{"b": 2}')])

        assert params['a'] == 1
        assert params['b'] == 2

    def test_later_message_wins_on_conflict(self):
        params = extract_function_params(
            [message('{"x": "first"}'), message('{"x": "last"}')]
        )

        assert params['x'] == 'last'

    def test_payloads_grouped_by_producing_node(self):
        params = extract_function_params(
            [
                message('{"merged": true}', node='stage_one'),
                message('{"quality": "ok"}', node='stage_two'),
            ]
        )

        assert params['node_outputs'] == {
            'stage_one': [{'merged': True}],
            'stage_two': [{'quality': 'ok'}],
        }

    def test_repeated_node_collects_a_list(self):
        """A ForEach forwards N results all tagged with its own node name."""
        params = extract_function_params(
            [
                message('{"doc": 1}', node='iterate'),
                message('{"doc": 2}', node='iterate'),
                message('{"doc": 3}', node='iterate'),
            ]
        )

        assert params['node_outputs']['iterate'] == [
            {'doc': 1},
            {'doc': 2},
            {'doc': 3},
        ]

    def test_input_list_preserves_order(self):
        params = extract_function_params([message('{"n": 1}'), message('{"n": 2}')])

        assert params['input_list'] == [{'n': 1}, {'n': 2}]

    def test_untagged_messages_are_absent_from_node_outputs(self):
        params = extract_function_params([message('{"a": 1}')])

        assert params['node_outputs'] == {}
        assert params['input_list'] == [{'a': 1}]

    def test_non_json_earlier_message_is_skipped(self):
        """A wider input_filter can now select raw documents, which are not JSON."""
        params = extract_function_params(
            [
                message('a raw uploaded document', node='input'),
                message('{"parsed": true}', node='extractor'),
            ]
        )

        assert params['parsed'] is True
        assert params['node_outputs'] == {'extractor': [{'parsed': True}]}

    def test_non_json_last_message_raises_even_with_valid_earlier_ones(self):
        with pytest.raises(ValueError, match='Invalid JSON'):
            extract_function_params(
                [message('{"good": 1}'), message('trailing garbage')]
            )

    def test_non_text_earlier_message_is_skipped(self):
        """An uploaded document's content is not a str at all."""
        document = UserMessage(
            content=DocumentMessageContent(
                base64='JVBERi0=', mime_type='application/pdf'
            ),
            metadata={'node': 'input'},
        )

        params = extract_function_params([document, message('{"parsed": true}')])

        assert params['parsed'] is True

    def test_non_text_last_message_raises(self):
        """The last input is the one the node is fed, so an unreadable one must
        fail rather than let the function run on the earlier messages' params.
        """
        document = UserMessage(
            content=DocumentMessageContent(
                base64='JVBERi0=', mime_type='application/pdf'
            )
        )

        with pytest.raises(ValueError, match='DocumentMessageContent'):
            extract_function_params([message('{"good": 1}'), document])

    def test_wrapped_text_is_read_like_a_bare_string(self):
        """The raw workflow input is a TextMessageContent when the caller posts
        the chat-style [{"role": "user", "content": ...}] form and a bare string
        when it posts a plain string. Identical text either way, so a node that
        reads the workflow input must not work for one caller and fail for the
        other."""
        wrapped = UserMessage(content=TextMessageContent(text='{"run_id": "abc"}'))

        assert extract_function_params([wrapped])['run_id'] == 'abc'

    def test_wrapped_non_json_last_message_still_raises(self):
        """Unwrapping must not weaken the JSON check — only the container type
        changed, not what counts as a readable payload."""
        wrapped = UserMessage(content=TextMessageContent(text='look up run abc'))

        with pytest.raises(ValueError, match='Invalid JSON'):
            extract_function_params([wrapped])

    def test_wrapped_text_is_attributed_to_its_node(self):
        """Unwrapping happens before attribution, so a wrapped payload is still
        grouped under the node that produced it."""
        wrapped = UserMessage(
            content=TextMessageContent(text='{"run_id": "abc"}'),
            metadata={'node': 'input'},
        )

        params = extract_function_params([wrapped])

        assert params['node_outputs']['input'] == [{'run_id': 'abc'}]

    def test_a_repeated_message_is_judged_by_position(self):
        """The same object can appear twice. Only its last position is the
        contractual input; an earlier occurrence must still be skippable.
        """
        repeated = message('not json')

        params = extract_function_params([repeated, message('{"ok": 1}')])

        assert params['ok'] == 1


class TestUnreadableInputIsJudgedByWhatWentMissing:
    """A node used as the start node is handed whatever the caller typed, which
    is usually prose. Whether that matters depends on whether the node needed it:
    one with every argument prefilled in the YAML never reads its input at all.
    """

    async def test_fully_prefilled_node_runs_on_unreadable_input(self):
        async def fetch(datasource_id: str, query_id: str, params=None):
            return f'{datasource_id}/{query_id}/{params}'

        adapter = create_function_node_adapter(fetch, 'fetch')

        result = await adapter(
            inputs=[message('run')],
            datasource_id='ds-1',
            query_id='q-1',
            params={'p_id': 'abc'},
        )

        assert result == "ds-1/q-1/{'p_id': 'abc'}"

    async def test_missing_param_still_fails_and_explains_why(self):
        """Deferring the failure must not hide it: the report has to name the
        absent parameter *and* say the message carrying it was unreadable."""

        async def fetch(datasource_id: str, query_id: str):
            return 'unreachable'

        adapter = create_function_node_adapter(fetch, 'fetch')

        with pytest.raises(ValueError) as excinfo:
            await adapter(inputs=[message('run')], datasource_id='ds-1')

        assert 'query_id' in str(excinfo.value)
        assert 'could not be read' in str(excinfo.value)
        assert 'Invalid JSON' in str(excinfo.value)

    async def test_error_does_not_reproduce_the_input(self):
        """Inputs carry workflow payloads. This error is raised to the caller and
        written to the logs by _validate_required_params, so the text must not
        travel with it — the producing node and the size locate the problem
        without reproducing anything.

        Scoped to what this module controls. flo_ai logs the raw string itself in
        FloUtils.extract_jsons_from_string ('No JSON found in strict mode: ...'),
        which no change here can suppress.
        """
        secret = '{"customer": "acme", "ssn": "123-45-6789"'  # truncated JSON

        async def call_service(service_id: str, action: str):
            return 'unreachable'

        adapter = create_function_node_adapter(call_service, 'call_service')

        with pytest.raises(ValueError) as excinfo:
            await adapter(inputs=[message(secret, node='upstream')], service_id='s-1')

        reported = str(excinfo.value)
        assert 'acme' not in reported and '123-45-6789' not in reported
        assert "'upstream'" in reported
        assert f'{len(secret)} chars' in reported

    async def test_unreadable_last_input_still_fails_when_an_earlier_one_parsed(self):
        """The stale-data case. If any input was read, the node is consulting its
        inputs, and the unreadable one is the message it was contractually fed —
        running on an earlier message's value silently substitutes older data for
        the thing it was supposed to act on.
        """

        async def fetch(datasource_id: str, query_id: str):
            return 'unreachable'

        adapter = create_function_node_adapter(fetch, 'fetch')

        readable = message('{"query_id": "stale"}', node='agent_a')
        unreadable = message('sorry, I could not do that', node='agent_b')

        with pytest.raises(ValueError, match='Invalid JSON'):
            await adapter(inputs=[readable, unreadable], datasource_id='ds-1')

    async def test_kwargs_function_still_fails_on_unreadable_input(self):
        """A **kwargs function builds its payload out of the input, so there is
        no named parameter whose absence would reveal the problem — running it
        on an empty payload is the silent-wrong-data case the check exists for.
        """

        async def processor(message_processor_id: str, **kwargs):
            return 'unreachable'

        adapter = create_function_node_adapter(processor, 'processor')

        with pytest.raises(ValueError, match='Invalid JSON'):
            await adapter(inputs=[message('run')], message_processor_id='mp-1')

    async def test_kwargs_function_still_fails_on_unreadable_content_type(self):
        document = UserMessage(
            content=DocumentMessageContent(
                base64='JVBERi0=', mime_type='application/pdf'
            )
        )

        async def processor(message_processor_id: str, **kwargs):
            return 'unreachable'

        adapter = create_function_node_adapter(processor, 'processor')

        with pytest.raises(ValueError, match='DocumentMessageContent'):
            await adapter(inputs=[document], message_processor_id='mp-1')

    async def test_readable_input_is_still_read(self):
        """The deferral must not stop a usable input being used."""

        async def fetch(datasource_id: str, query_id: str):
            return f'{datasource_id}/{query_id}'

        adapter = create_function_node_adapter(fetch, 'fetch')

        result = await adapter(
            inputs=[message('{"query_id": "from_input"}')], datasource_id='ds-1'
        )

        assert result == 'ds-1/from_input'


class TestFixedSignatureDispatch:
    async def test_only_named_params_are_forwarded(self):
        received = {}

        async def insert_rows(datasource_id: str, table_name: str, data):
            received.update(
                datasource_id=datasource_id, table_name=table_name, data=data
            )
            return 'ok'

        adapter = create_function_node_adapter(insert_rows, 'insert_rows')
        await adapter(
            inputs=[message('{"table_name": "people", "data": [{"n": 1}]}')],
            variables={'unrelated': 'ignored'},
            datasource_id='ds-1',
        )

        assert received == {
            'datasource_id': 'ds-1',
            'table_name': 'people',
            'data': [{'n': 1}],
        }

    async def test_missing_required_param_is_reported(self):
        async def insert_rows(datasource_id: str, table_name: str):
            return 'ok'

        adapter = create_function_node_adapter(insert_rows, 'insert_rows')

        with pytest.raises(ValueError, match='table_name'):
            await adapter(inputs=[message('{}')], datasource_id='ds-1')


class TestVarKeywordDispatch:
    async def test_dynamic_params_reach_a_kwargs_function(self):
        received = {}

        async def run_processor(processor_id: str, **kwargs):
            received.update(processor_id=processor_id, kwargs=kwargs)
            return 'ok'

        adapter = create_function_node_adapter(run_processor, 'run_processor')
        await adapter(
            inputs=[message('{"merged": true}', node='stage_one')],
            variables={'_wf_execution_id': 'run-1'},
            processor_id='mp-1',
        )

        assert received['processor_id'] == 'mp-1'
        assert received['kwargs']['_wf_execution_id'] == 'run-1'
        assert received['kwargs']['node_outputs'] == {'stage_one': [{'merged': True}]}

    async def test_kwargs_is_not_treated_as_a_required_param(self):
        """``**kwargs`` reports no default, but it is a collector, not an argument."""

        async def run_processor(processor_id: str, **kwargs):
            return 'ok'

        adapter = create_function_node_adapter(run_processor, 'run_processor')

        result = await adapter(inputs=[message('{}')], processor_id='mp-1')

        assert result == 'ok'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
