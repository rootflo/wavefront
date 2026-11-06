from fastapi import HTTPException, Request, status


def require_secret_access(request: Request) -> None:
    """Allow plaintext secrets only for callers the auth middleware marked as
    internal services (mTLS, or passthrough outside production)."""
    if not getattr(request.state, 'secret_access', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Secrets are only returned to internal services',
        )
