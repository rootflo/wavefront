import pytest

from flo_cloud.postgres.postgres import PostgresClient


def convert(query, params):
    # _convert_named_params reads nothing from the instance.
    return PostgresClient._convert_named_params(None, query, params)[0]


def test_placeholders_become_pyformat():
    assert convert(
        'SELECT * FROM t WHERE id = :id AND n > :min_n', {'id': 1, 'min_n': 2}
    ) == ('SELECT * FROM t WHERE id = %(id)s AND n > %(min_n)s')


@pytest.mark.parametrize(
    'query, expected',
    [
        # #465: ':MI' inside a literal is part of the format string.
        (
            "SELECT to_char(t, 'HH24:MI') FROM x WHERE id = :id",
            "SELECT to_char(t, 'HH24:MI') FROM x WHERE id = %(id)s",
        ),
        ("SELECT 'it''s :id' WHERE id = :id", "SELECT 'it''s :id' WHERE id = %(id)s"),
        (
            'SELECT "col:id" FROM x WHERE id = :id',
            'SELECT "col:id" FROM x WHERE id = %(id)s',
        ),
        (
            'SELECT $$a:id$$, $q$b:id$q$ WHERE id = :id',
            'SELECT $$a:id$$, $q$b:id$q$ WHERE id = %(id)s',
        ),
        ('SELECT 1 -- :id\nWHERE id = :id', 'SELECT 1 -- :id\nWHERE id = %(id)s'),
        ('SELECT /* :id */ 1 WHERE id = :id', 'SELECT /* :id */ 1 WHERE id = %(id)s'),
        ('SELECT t::text WHERE id = :id', 'SELECT t::text WHERE id = %(id)s'),
        (
            "SELECT E'it\\'s :id' WHERE id = :id",
            "SELECT E'it\\'s :id' WHERE id = %(id)s",
        ),
        ('SELECT $q1$a:id$q1$ WHERE id = :id', 'SELECT $q1$a:id$q1$ WHERE id = %(id)s'),
    ],
)
def test_colons_in_literals_comments_and_casts_are_kept(query, expected):
    assert convert(query, {'id': 1}) == expected


def test_a_name_that_is_not_a_parameter_is_kept():
    assert (
        convert('SELECT :other WHERE id = :id', {'id': 1})
        == 'SELECT :other WHERE id = %(id)s'
    )


def test_percent_signs_are_escaped_for_psycopg2():
    assert convert(
        "SELECT * FROM x WHERE name LIKE 'abc%' AND n % 2 = :r", {'r': 0}
    ) == ("SELECT * FROM x WHERE name LIKE 'abc%%' AND n %% 2 = %(r)s")


def test_a_query_without_params_is_unchanged():
    query = "SELECT to_char(t, 'HH24:MI'), 'abc%'"
    assert convert(query, None) == query
    assert convert(query, {}) == query


def test_existing_pyformat_placeholders_and_escaped_percents_are_kept():
    # list_tables() and the other metadata queries already use %(name)s.
    query = "SELECT * FROM t WHERE table_schema = %(table_schema)s AND n % 2 = :r AND name LIKE 'a%%'"
    assert convert(query, {'table_schema': 'public', 'r': 0}) == (
        "SELECT * FROM t WHERE table_schema = %(table_schema)s AND n %% 2 = %(r)s AND name LIKE 'a%%'"
    )
