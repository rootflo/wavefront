"""A write Postgres refuses over a NUL character comes back as an error naming
where the NUL is, instead of an opaque 500. Writes it accepts are left alone."""

from unittest.mock import MagicMock

import psycopg2.errors
import pytest
from flo_cloud.postgres import PostgresClient, UnstorableValueError

JSONB_NUL = psycopg2.errors.UntranslatableCharacter(
    'unsupported Unicode escape sequence'
)
TEXT_NUL = ValueError('A string literal cannot contain NUL (0x00) characters.')


@pytest.fixture
def client():
    client = PostgresClient(host='h', schema='tenant')
    client.get_connection = MagicMock()
    return client


def _cursor(client):
    return client.get_connection.return_value.__enter__.return_value.cursor.return_value


def test_jsonb_refusal_lists_candidates(client):
    """Postgres does not name the refused value, so every JSON NUL is a candidate."""
    _cursor(client).executemany.side_effect = JSONB_NUL
    row = {'id': 1, 'meta': {'tags': ['alpha', '\x00 - \x00']}, 'extra': {'k': '\x00'}}

    with pytest.raises(UnstorableValueError) as raised:
        client.insert_rows_json('orders', [row])

    assert str(raised.value) == (
        "Table 'orders' refused a NUL character (\\u0000) in a JSON value; "
        'JSON values containing one: row 0 meta.tags[1], row 0 extra.k'
    )


def test_candidate_list_is_capped(client):
    _cursor(client).executemany.side_effect = JSONB_NUL
    rows = [{'meta': {'k': '\x00'}} for _ in range(7)]

    with pytest.raises(UnstorableValueError, match=r'row 4 meta\.k and 2 more$'):
        client.insert_rows_json('orders', rows)


def test_nul_in_a_text_column_is_located(client):
    _cursor(client).executemany.side_effect = TEXT_NUL

    with pytest.raises(UnstorableValueError, match="Row 1 of table 'notes': body "):
        client.insert_rows_json('notes', [{'body': 'ok'}, {'body': 'a\x00b'}])


def test_text_refusal_names_the_text_column_not_an_accepted_json_nul(client):
    """The json column stores its escaped NUL; only the plain string is refused."""
    _cursor(client).executemany.side_effect = TEXT_NUL
    row = {'payload': {'note': 'a\x00b'}, 'body': 'c\x00d'}

    with pytest.raises(UnstorableValueError) as raised:
        client.insert_rows_json('events', [row])

    assert str(raised.value) == (
        "Row 0 of table 'events': body contains a NUL character (\\u0000), "
        'which Postgres cannot store'
    )


def test_a_nul_the_column_accepts_is_written(client):
    """json and text columns store an escaped NUL, so nothing is refused up front."""
    client.insert_rows_json('events', [{'payload': {'note': 'a\x00b'}}])

    _cursor(client).executemany.assert_called_once()


def test_other_errors_are_not_relabelled(client):
    """A NUL only inside JSON cannot cause psycopg2's ValueError."""
    _cursor(client).executemany.side_effect = ValueError('something else')

    with pytest.raises(ValueError, match='something else') as raised:
        client.insert_rows_json('notes', [{'body': 'clean', 'meta': {'k': '\x00'}}])

    assert not isinstance(raised.value, UnstorableValueError)


def test_multi_insert_names_the_failing_table(client):
    _cursor(client).executemany.side_effect = [None, JSONB_NUL]
    inserts = [
        {'table_name': 'orders', 'data': [{'id': 1}]},
        {'table_name': 'order_items', 'data': [{'notes': ['\x00']}]},
    ]

    with pytest.raises(
        UnstorableValueError, match=r"Table 'order_items' .*: row 0 notes\[0\]$"
    ):
        client.insert_rows_json_multi(inserts)


def test_update_is_located(client):
    _cursor(client).execute.side_effect = JSONB_NUL

    with pytest.raises(
        UnstorableValueError, match=r'containing one: row 0 meta\.name$'
    ):
        client.update_rows_json('t', {'meta': {'name': '\x00'}}, 'id = :id', {'id': 1})


def test_non_ascii_text_is_serialised_unchanged(client):
    _, serialized = client._build_insert(
        'orders', [{'meta': {'tags': ['café – naïve']}}]
    )

    assert serialized[0]['meta'].adapted == {'tags': ['café – naïve']}
