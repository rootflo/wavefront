"""Chatbot name uniqueness must be scoped to live rows.

Deletes are soft. A plain UniqueConstraint on (namespace, name) lets a deleted
row keep reserving its name forever, so deleting `support-bot` and creating it
again -- a routine admin action -- fails against a chatbot that appears nowhere
in the UI, with an "already exists" error naming something the caller cannot
see. `agents` can use a table-level constraint because it hard-deletes.

Asserted on the ORM metadata rather than against a live database: the failure
mode is someone simplifying the partial index back into a UniqueConstraint,
which this catches without needing Postgres.
"""

from db_repo_module.models.chatbot import Chatbot

INDEX_NAME = 'uq_chatbots_namespace_name_active'


def _partial_unique_index():
    return next(
        (index for index in Chatbot.__table__.indexes if index.name == INDEX_NAME),
        None,
    )


def test_a_partial_unique_index_exists():
    index = _partial_unique_index()
    assert index is not None, f'{INDEX_NAME} is missing from the Chatbot metadata'
    assert index.unique, 'the index must be unique or it enforces nothing'


def test_it_covers_namespace_and_name_in_that_order():
    index = _partial_unique_index()
    assert [column.name for column in index.columns] == ['namespace', 'name']


def test_it_is_restricted_to_live_rows():
    index = _partial_unique_index()
    where = index.dialect_options['postgresql'].get('where')
    assert where is not None, (
        'without a WHERE clause this is a global unique index, and a '
        'soft-deleted chatbot keeps its name reserved'
    )

    # Normalised rather than compared verbatim: `text('is_deleted = false')`
    # and `Chatbot.is_deleted.is_(False)` mean the same thing but stringify
    # differently ('is_deleted = false' vs 'chatbots.is_deleted IS false'), and
    # a spelling change should not fail this test.
    predicate = ' '.join(str(where).lower().split())

    assert 'is_deleted' in predicate
    # The value matters as much as the column. `is_deleted = true` would invert
    # the index -- uniqueness enforced across deleted rows only, so two live
    # chatbots could share a name -- and would satisfy a bare column-name check.
    assert predicate.endswith(
        'false'
    ), f'predicate must restrict the index to live rows, got: {predicate}'


def test_no_table_level_unique_constraint_on_the_name():
    # A UniqueConstraint alongside the partial index would reintroduce the bug
    # while the index above still looked correct.
    offenders = [
        constraint
        for constraint in Chatbot.__table__.constraints
        if getattr(constraint, 'columns', None) is not None
        and {'namespace', 'name'} <= {column.name for column in constraint.columns}
        and type(constraint).__name__ == 'UniqueConstraint'
    ]
    assert not offenders, (
        'name uniqueness must be the partial index only; a table-level '
        'UniqueConstraint also binds soft-deleted rows'
    )
