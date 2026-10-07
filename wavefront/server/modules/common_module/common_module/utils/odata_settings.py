"""Cloud-specific OData parameter style, wired from ``[cloud] platform``."""

_cloud_provider: str = ''


def configure_odata_cloud_provider(provider: str | None) -> None:
    global _cloud_provider
    _cloud_provider = (provider or '').lower()


def odata_parameter_char(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    return '@' if _cloud_provider == 'gcp' else ':'
