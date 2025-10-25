#!/usr/bin/env python3
"""
Pytest tests for the FloUtils utility methods.
"""

import sys
import os
import pytest

# Add the flo_ai directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flo_ai.utils.flo_utils import FloUtils


class TestFloUtils:
    """Test cases for FloUtils class methods."""

    def test_strip_comments_from_string_single_line_comments(self):
        """Test removal of single-line comments (//)."""
        input_str = '{"name": "test", // this is a comment\n"value": 123}'
        expected = '{"name": "test", \n"value": 123}'
        result = FloUtils.strip_comments_from_string(input_str)
        assert result == expected

    def test_strip_comments_from_string_multi_line_comments(self):
        """Test removal of multi-line comments (/* */)."""
        input_str = '{"name": "test", /* this is a\nmulti-line comment */ "value": 123}'
        expected = '{"name": "test",  "value": 123}'
        result = FloUtils.strip_comments_from_string(input_str)
        assert result == expected

    def test_strip_comments_from_string_mixed_comments(self):
        """Test removal of both single-line and multi-line comments."""
        input_str = """{"name": "test", // single line comment
        /* multi-line 
           comment */ "value": 123 // another single line}"""
        expected = """{"name": "test", 
         "value": 123 """
        result = FloUtils.strip_comments_from_string(input_str)
        assert result == expected

    def test_strip_comments_from_string_with_strings_containing_comment_chars(self):
        """Test that comment characters inside strings are preserved."""
        input_str = (
            '{"url": "http://example.com", "comment": "This /* is not */ a comment"}'
        )
        expected = (
            '{"url": "http://example.com", "comment": "This /* is not */ a comment"}'
        )
        result = FloUtils.strip_comments_from_string(input_str)
        assert result == expected

    def test_strip_comments_from_string_with_escaped_quotes(self):
        """Test handling of escaped quotes in strings."""
        input_str = '{"message": "He said \\"Hello\\"", // comment\n"value": 42}'
        expected = '{"message": "He said \\"Hello\\"", \n"value": 42}'
        result = FloUtils.strip_comments_from_string(input_str)
        assert result == expected

    def test_strip_comments_from_string_no_comments(self):
        """Test that strings without comments are returned unchanged."""
        input_str = '{"name": "test", "value": 123, "active": true}'
        result = FloUtils.strip_comments_from_string(input_str)
        assert result == input_str

    def test_strip_comments_from_string_empty_string(self):
        """Test handling of empty string."""
        result = FloUtils.strip_comments_from_string('')
        assert result == ''

    def test_strip_comments_from_string_only_comments(self):
        """Test string that is only comments."""
        input_str = '// just a comment\n/* and another */'
        expected = '\n'
        result = FloUtils.strip_comments_from_string(input_str)
        assert result == expected

    def test_extract_jsons_from_string_single_json(self):
        """Test extraction of a single JSON object."""
        input_str = 'Some text {"name": "test", "value": 123} more text'
        expected = {'name': 'test', 'value': 123}
        result = FloUtils.extract_jsons_from_string(input_str)
        assert result == expected

    def test_extract_jsons_from_string_multiple_jsons(self):
        """Test extraction and merging of multiple JSON objects."""
        input_str = 'Text {"name": "test"} more {"value": 123, "active": true} end'
        expected = {'name': 'test', 'value': 123, 'active': True}
        result = FloUtils.extract_jsons_from_string(input_str)
        assert result == expected

    def test_extract_jsons_from_string_overlapping_keys(self):
        """Test that later JSON objects override earlier ones for same keys."""
        input_str = (
            '{"name": "first", "value": 100} {"name": "second", "extra": "data"}'
        )
        expected = {'name': 'second', 'value': 100, 'extra': 'data'}
        result = FloUtils.extract_jsons_from_string(input_str)
        assert result == expected

    def test_extract_jsons_from_string_nested_objects(self):
        """Test extraction of nested JSON objects."""
        input_str = 'Data {"user": {"name": "test", "id": 123}, "active": true} end'
        expected = {'user': {'name': 'test', 'id': 123}, 'active': True}
        result = FloUtils.extract_jsons_from_string(input_str)
        assert result == expected

    def test_extract_jsons_from_string_with_comments(self):
        """Test extraction of JSON with comments that need stripping."""
        input_str = """Text {"name": "test", // comment
        "value": 123 /* another comment */} end"""
        expected = {'name': 'test', 'value': 123}
        result = FloUtils.extract_jsons_from_string(input_str)
        assert result == expected

    def test_extract_jsons_from_string_no_json(self):
        """Test behavior when no JSON is found in non-strict mode."""
        input_str = 'This is just plain text with no JSON objects'
        result = FloUtils.extract_jsons_from_string(input_str)
        assert result == {}

    def test_extract_jsons_from_string_no_json_strict_mode(self):
        """Test that strict mode raises ValueError when no JSON is found."""
        input_str = 'This is just plain text with no JSON objects'
        with pytest.raises(ValueError, match='No JSON found in strict mode'):
            FloUtils.extract_jsons_from_string(input_str, strict=True)

    def test_extract_jsons_from_string_invalid_json(self):
        """Test handling of invalid JSON (should be skipped)."""
        input_str = (
            'Valid: {"name": "test"} Invalid: {invalid json} Valid: {"value": 123}'
        )
        expected = {'name': 'test', 'value': 123}
        result = FloUtils.extract_jsons_from_string(input_str)
        assert result == expected

    def test_extract_jsons_from_string_empty_string(self):
        """Test behavior with empty string."""
        result = FloUtils.extract_jsons_from_string('')
        assert result == {}

    def test_extract_jsons_from_string_empty_string_strict(self):
        """Test strict mode with empty string."""
        with pytest.raises(ValueError, match='No JSON found in strict mode'):
            FloUtils.extract_jsons_from_string('', strict=True)

    def test_extract_jsons_from_string_malformed_braces(self):
        """Test handling of malformed brace structures."""
        input_str = 'Text { invalid { structure } more text {"valid": true}'
        expected = {'valid': True}
        result = FloUtils.extract_jsons_from_string(input_str)
        assert result == expected

    def test_extract_jsons_from_string_arrays(self):
        """Test extraction of JSON objects containing arrays."""
        input_str = 'Data {"items": [1, 2, 3], "name": "test"} end'
        expected = {'items': [1, 2, 3], 'name': 'test'}
        result = FloUtils.extract_jsons_from_string(input_str)
        assert result == expected

    def test_extract_jsons_from_string_complex_nested(self):
        """Test extraction of complex nested JSON structures."""
        input_str = """Text {"config": {"database": {"host": "localhost", "port": 5432}, 
        "features": ["auth", "logging"]}, "version": "1.0"} end"""
        expected = {
            'config': {
                'database': {'host': 'localhost', 'port': 5432},
                'features': ['auth', 'logging'],
            },
            'version': '1.0',
        }
        result = FloUtils.extract_jsons_from_string(input_str)
        assert result == expected

    def test_extract_jsons_from_string_unicode_content(self):
        """Test handling of Unicode content in JSON."""
        input_str = 'Text {"message": "Hello 世界", "emoji": "🚀"} end'
        expected = {'message': 'Hello 世界', 'emoji': '🚀'}
        result = FloUtils.extract_jsons_from_string(input_str)
        assert result == expected

    def test_extract_jsons_from_string_boolean_and_null(self):
        """Test extraction of JSON with boolean and null values."""
        input_str = 'Data {"active": true, "disabled": false, "data": null} end'
        expected = {'active': True, 'disabled': False, 'data': None}
        result = FloUtils.extract_jsons_from_string(input_str)
        assert result == expected

    def test_strip_comments_incomplete_multiline_comment(self):
        """Test handling of incomplete multi-line comments."""
        input_str = '{"name": "test", /* incomplete comment'
        expected = '{"name": "test", t'
        result = FloUtils.strip_comments_from_string(input_str)
        assert result == expected

    def test_strip_comments_forward_slash_not_comment(self):
        """Test that single forward slashes that don't form comments are preserved."""
        input_str = '{"url": "https://example.com/path", "ratio": "1/2"}'
        result = FloUtils.strip_comments_from_string(input_str)
        assert result == input_str

    def test_extract_jsons_from_string_deeply_nested(self):
        """Test extraction with very deeply nested objects."""
        input_str = 'Text {"a": {"b": {"c": {"d": {"e": "deep"}}}}} end'
        expected = {'a': {'b': {'c': {'d': {'e': 'deep'}}}}}
        result = FloUtils.extract_jsons_from_string(input_str)
        assert result == expected
