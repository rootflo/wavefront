"""Checks for the caller-supplied fragments that end up inside SQL text.

Table names and the $select / $orderby / $groupby clauses are interpolated into
queries rather than bound as parameters, so each is held to a small grammar:
identifiers, column references, '*', the common aggregates and sort directions.
Anything else - subqueries, other function calls, quotes, comments, statement
separators - is refused, which is what keeps a caller from reading tables (the
database's own catalogs included) other than the one the request names.
"""

import re
from typing import Optional


class InvalidResourceError(ValueError):
    """A caller-supplied table name this datasource refuses to query."""


class InvalidQueryError(ValueError):
    """A $select, $orderby or $groupby clause outside the allowed grammar."""


IDENTIFIER_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
TABLE_NAME_MAX_LEN = 512
CLAUSE_MAX_LEN = 4096

_IDENT = r'[A-Za-z_][A-Za-z0-9_]*'
# Keywords that read like a column but evaluate to session details (the login,
# the schema) without needing parentheses.
_SESSION_KEYWORD = (
    r'(?:current_user|session_user|system_user|current_role|current_schema'
    r'|current_catalog|user)\b'
)
# A column, optionally qualified by its table or join alias.
_REF = rf'(?!{_SESSION_KEYWORD}){_IDENT}(?:\.{_IDENT})?'
_AGGREGATE = rf'(?:count|sum|avg|min|max)\s*\(\s*(?:\*|(?:distinct\s+)?{_REF})\s*\)'
_ALIAS = rf'(?:\s+(?:as\s+)?{_IDENT})?'

_SELECT_ITEM_RE = re.compile(
    rf'\*|{_IDENT}\.\*|(?:{_AGGREGATE}|{_REF}){_ALIAS}', re.IGNORECASE
)
_ORDER_BY_ITEM_RE = re.compile(
    rf'(?:{_AGGREGATE}|{_REF})(?:\s+(?:asc|desc))?', re.IGNORECASE
)
_GROUP_BY_ITEM_RE = re.compile(_REF, re.IGNORECASE)


def _validate_clause(value: Optional[str], item_re: re.Pattern, clause: str) -> None:
    if not value:
        return
    # No allowed item contains a comma, so splitting on them is exact.
    if len(value) > CLAUSE_MAX_LEN or not all(
        item_re.fullmatch(item.strip()) for item in value.split(',')
    ):
        raise InvalidQueryError(f'Invalid {clause}: {value}')


def validate_select(value: Optional[str]) -> None:
    _validate_clause(value, _SELECT_ITEM_RE, '$select')


def validate_order_by(value: Optional[str]) -> None:
    _validate_clause(value, _ORDER_BY_ITEM_RE, '$orderby')


def validate_group_by(value: Optional[str]) -> None:
    _validate_clause(value, _GROUP_BY_ITEM_RE, '$groupby')
