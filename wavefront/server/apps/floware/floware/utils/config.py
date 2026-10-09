def csv(value: str | None, default: tuple[str, ...] = ()) -> list[str]:
    """Split a comma-separated config value; ``default`` when it is not set."""
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(',') if item.strip()]
