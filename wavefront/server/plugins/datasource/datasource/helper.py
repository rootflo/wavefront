from .types import Meta


def construct_meta(status: str, message: str = '', code: int = 1) -> Meta:
    return Meta(status=status, message=message, code=code)
