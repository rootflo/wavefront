"""Pgvector vs Text column stand-ins for SQLAlchemy models.

Production uses pgvector types. Pytest enables text stand-ins before models load
via ``enable_pgvector_test_standins()`` in the flo_testing plugin.
"""

_use_pgvector_test_standins = False


def enable_pgvector_test_standins() -> None:
    global _use_pgvector_test_standins
    _use_pgvector_test_standins = True


def use_pgvector_columns() -> bool:
    return not _use_pgvector_test_standins
