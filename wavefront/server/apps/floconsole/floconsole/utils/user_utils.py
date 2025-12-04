from fastapi import Request


def get_current_user(req: Request):
    return (
        req.state.session.role_id,
        req.state.session.user_id,
        req.state.session.session_id
        if hasattr(req.state, 'session') and req.state.session
        else None,
    )
