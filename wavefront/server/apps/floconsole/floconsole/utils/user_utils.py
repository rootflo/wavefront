from fastapi import Request


def get_current_user(req: Request):
    """(role_id, user_id, session_id) of the authenticated caller."""
    principal = req.state.principal
    return principal.role_id, principal.id, principal.session_id
