"""Parsing the [extensions] remotes setting: bad input never breaks the console."""

import pytest

from floconsole.services.extension_settings import parse_extensions

REMOTE = {'name': 'access', 'entry': 'https://ui.example.com/remoteEntry.js'}


@pytest.mark.parametrize('raw', [None, '', '   ', '[]'])
def test_none_configured(raw):
    assert parse_extensions(raw) == []


def test_reads_remotes_with_module_as_the_default_type():
    raw = '[{"name": "access", "entry": "https://ui.example.com/remoteEntry.js"}]'
    assert parse_extensions(raw) == [{**REMOTE, 'type': 'module'}]


@pytest.mark.parametrize('raw', ['not json', '{"name": "x"}', '"x"'])
def test_malformed_setting_loads_nothing(raw):
    assert parse_extensions(raw) == []


def test_bad_entries_are_skipped_and_good_ones_kept():
    raw = (
        '[{"name": "access", "entry": "https://ui.example.com/remoteEntry.js"},'
        ' {"name": "no-entry"}, "string", {"name": "", "entry": "x"},'
        ' {"name": "odd", "entry": "x", "type": "systemjs"},'
        ' {"name": "access", "entry": "https://other/remoteEntry.js"},'
        ' {"name": "legacy", "entry": "https://l/remoteEntry.js", "type": "var"}]'
    )
    assert parse_extensions(raw) == [
        {**REMOTE, 'type': 'module'},
        {'name': 'legacy', 'entry': 'https://l/remoteEntry.js', 'type': 'var'},
    ]
