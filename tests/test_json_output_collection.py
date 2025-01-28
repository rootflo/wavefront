import pytest
import json
from flo_ai.error.flo_exception import FloException
from flo_ai.state.flo_output_collector import FloOutputCollector
from flo_ai.state.flo_json_output_collector import FloJsonOutputCollector


class TestFloJsonOutputCollector:
    @pytest.fixture
    def collector(self):
        return FloJsonOutputCollector(strict=False)

    @pytest.fixture
    def strict_collector(self):
        return FloJsonOutputCollector(strict=True)

    def test_initialization(self, collector):
        assert isinstance(collector, FloOutputCollector)
        assert collector.strict is False
        assert collector.data == []

    def test_append_single_json(self, collector):
        test_input = '{"key": "value"}'
        collector.append(test_input)
        assert collector.data == [{'key': 'value'}]

    def test_append_multiple_jsons(self, collector):
        test_input = '{"key1": "value1"} Some text {"key2": "value2"}'
        collector.append(test_input)
        assert collector.data == [{'key1': 'value1', 'key2': 'value2'}]

    def test_append_nested_json(self, collector):
        test_input = '{"outer": {"inner": "value"}}'
        collector.append(test_input)
        assert collector.data == [{'outer': {'inner': 'value'}}]

    def test_strip_comments(self, collector):
        test_input = """
        {
            // Single line comment
            "key1": "value1",
            /* Multi-line
               comment */
            "key2": "value2"
        }
        """
        collector.append(test_input)
        assert collector.data == [{'key1': 'value1', 'key2': 'value2'}]

    def test_string_with_comment_chars(self, collector):
        test_input = '{"key": "This // is not a comment", "url": "http://example.com"}'
        collector.append(test_input)
        assert collector.data == [
            {'key': 'This // is not a comment', 'url': 'http://example.com'}
        ]

    def test_strict_mode_no_json(self, strict_collector):
        with pytest.raises(FloException) as exc_info:
            strict_collector.append('No JSON here')
        assert exc_info.value.error_code == 1099

    def test_strict_mode_with_json(self, strict_collector):
        test_input = '{"key": "value"}'
        strict_collector.append(test_input)
        assert strict_collector.data == [{'key': 'value'}]

    def test_pop_operation(self, collector: FloJsonOutputCollector):
        test_input1 = '{"key1": "value1"}'
        test_input2 = '{"key2": "value2"}'
        collector.append(test_input1)
        collector.append(test_input2)

        popped = collector.pop()
        assert popped == {'key2': 'value2'}
        assert len(collector.data) == 1

    def test_peek_operation(self, collector: FloJsonOutputCollector):
        test_input = '{"key": "value"}'
        collector.append(test_input)

        peeked = collector.peek()
        assert peeked == {'key': 'value'}
        assert len(collector.data) == 1

    def test_peek_empty_collector(self, collector):
        assert collector.peek() is None

    def test_fetch_operation(self, collector: FloJsonOutputCollector):
        test_input1 = '{"key1": "value1"}'
        test_input2 = '{"key2": "value2"}'
        collector.append(test_input1)
        collector.append(test_input2)

        result = collector.fetch()
        assert result == {'key1': 'value1', 'key2': 'value2'}

    def test_fetch_with_overlapping_keys(self, collector: FloJsonOutputCollector):
        test_input1 = '{"key": "value1"}'
        test_input2 = '{"key": "value2"}'
        collector.append(test_input1)
        collector.append(test_input2)

        result = collector.fetch()
        assert result == {'key': 'value2'}  # Later values should override earlier ones

    def test_invalid_json(self, collector: FloJsonOutputCollector):
        test_input = '{"key": "value",}'  # Invalid JSON with trailing comma
        with pytest.raises(json.JSONDecodeError):
            collector.append(test_input)

    def test_complex_nested_structure(self, collector: FloJsonOutputCollector):
        test_input = """
        {
            "array": [1, 2, 3],
            "nested": {
                "deep": {
                    "deeper": "value"
                }
            },
            "mixed": [{"key": "value"}, 42, "string"]
        }
        """
        collector.append(test_input)
        expected = {
            'array': [1, 2, 3],
            'nested': {'deep': {'deeper': 'value'}},
            'mixed': [{'key': 'value'}, 42, 'string'],
        }
        assert collector.data == [expected]

    @pytest.mark.parametrize(
        'test_input,expected',
        [
            ('{"a": 1}', [{'a': 1}]),
            ('{"a": 1, "b": 2}', [{'a': 1, 'b': 2}]),
            ('{"a": 1} {"b": 2}', [{'a': 1, 'b': 2}]),
            ('No JSON', [{}]),
        ],
    )
    def test_various_inputs(
        self, collector: FloJsonOutputCollector, test_input, expected
    ):
        collector.append(test_input)
        assert collector.data == expected
