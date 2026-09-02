from uuid import UUID


def is_valid_uuid(value) -> bool:
    """Is ``value`` something Postgres will accept in a uuid column?

    Guards a query before it is issued: `id` columns are uuid, so a malformed
    string raises InvalidTextRepresentation and surfaces as a 500 with a SQL
    traceback, before the repository can return None. Checking first turns a
    mistyped id into the 400 or 404 it should have been.
    """
    try:
        UUID(str(value))
    except ValueError:
        return False
    return True
