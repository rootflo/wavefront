"""SQL dialect helpers for cross-engine OData/filter rendering."""

from abc import ABC
from abc import abstractmethod


class SqlDialect(ABC):
    """Dialect-specific rendering for shared SQL operations.

    OData/filter parsers stay dialect-agnostic and delegate string ops
    (and other engine-specific syntax) here.
    """

    def as_text(self, field: str) -> str:
        """Coerce ``field`` to a text type suitable for string operators.

        Default is a no-op. Dialects with semi-structured types (e.g. Redshift
        SUPER, BigQuery JSON) should CAST so ``LOWER`` / ``LIKE`` / ``ILIKE``
        receive a character type.
        """
        return field

    @abstractmethod
    def contains(self, field: str, param_ref: str) -> str:
        """Case-insensitive substring match of ``param_ref`` against ``field``.

        ``param_ref`` is the already-prefixed bind placeholder (e.g. ``:name``
        or ``@name``). Callers are responsible for wrapping the bound value
        with ``%...%`` wildcards.
        """
        raise NotImplementedError


class StandardSqlDialect(SqlDialect):
    """Portable LOWER/LIKE contains. Used as the default for tests and callers
    that do not select a concrete engine dialect.
    """

    def contains(self, field: str, param_ref: str) -> str:
        text_field = self.as_text(field)
        return f'LOWER({text_field}) LIKE LOWER({param_ref})'


class RedshiftSqlDialect(SqlDialect):
    """Redshift: CAST to VARCHAR so SUPER path expressions work with ILIKE."""

    def as_text(self, field: str) -> str:
        return f'CAST({field} AS VARCHAR)'

    def contains(self, field: str, param_ref: str) -> str:
        return f'{self.as_text(field)} ILIKE {param_ref}'


class PostgresSqlDialect(SqlDialect):
    """Postgres: native ILIKE for case-insensitive substring match."""

    def contains(self, field: str, param_ref: str) -> str:
        return f'{field} ILIKE {param_ref}'


class BigQuerySqlDialect(SqlDialect):
    """BigQuery: CAST to STRING then LOWER/LIKE."""

    def as_text(self, field: str) -> str:
        return f'CAST({field} AS STRING)'

    def contains(self, field: str, param_ref: str) -> str:
        text_field = self.as_text(field)
        return f'LOWER({text_field}) LIKE LOWER({param_ref})'


class MSSQLSqlDialect(SqlDialect):
    """MSSQL: CAST to NVARCHAR then LOWER/LIKE."""

    def as_text(self, field: str) -> str:
        return f'CAST({field} AS NVARCHAR(MAX))'

    def contains(self, field: str, param_ref: str) -> str:
        text_field = self.as_text(field)
        return f'LOWER({text_field}) LIKE LOWER({param_ref})'
