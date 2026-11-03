"""Request-level behaviour: what gets authenticated, what gets refused, and how."""

import pytest
from fastapi import APIRouter, Depends, FastAPI, WebSocket
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.requests import Request

from authz_module import (
    AuthenticationError,
    AuthzProvider,
    Legacy,
    Principal,
    current_principal,
    from_path,
    install,
    is_allowed,
    public_route,
    requires,
    user_principal,
)
from authz_module.middleware import AuthzMiddleware
from authz_module.testing import ScriptedAuthorizer

ALICE = user_principal('alice', role_id='member')


class HeaderAuthenticator:
    """'Bearer ok' is alice, 'Bearer bad' fails, no header is no credentials."""

    calls = 0

    async def authenticate(self, conn):
        HeaderAuthenticator.calls += 1
        header = conn.headers.get('Authorization')
        if header is None:
            return None
        if header == 'Bearer ok':
            return ALICE
        raise AuthenticationError('Invalid session')


def render(status_code, message):
    return JSONResponse({'error': message}, status_code=status_code)


router = APIRouter()


@router.get('/health', dependencies=[Depends(public_route)])
async def health():
    return {'ok': True}


@router.get(
    '/things/{thing_id}',
    dependencies=[
        Depends(
            requires(
                'test_mw:GetThing',
                resource=from_path('thing', 'thing_id'),
                legacy=Legacy.AUTHENTICATED,
            )
        )
    ],
)
async def get_thing(thing_id: str, request: Request):
    return {
        'thing': thing_id,
        'principal': request.state.principal.id,
        'contextvar': current_principal().id,
    }


@router.delete(
    '/things/{thing_id}',
    dependencies=[
        Depends(
            requires(
                'test_mw:DeleteThing',
                legacy=Legacy.ADMIN,
                deny_status=401,
                deny_message='Access denied',
            )
        )
    ],
)
async def delete_thing(thing_id: str):
    return {'deleted': thing_id}


@router.post(
    '/open', dependencies=[Depends(requires('test_mw:Open', legacy=Legacy.PUBLIC))]
)
async def open_action(request: Request):
    return {'anonymous': request.state.principal.is_anonymous}


@router.get(
    '/scoped',
    dependencies=[Depends(requires('test_mw:Scoped', legacy=Legacy.AUTHENTICATED))],
)
async def scoped(request: Request):
    return {'all': await is_allowed(request, 'test_mw:GetThing')}


@router.get('/undeclared')
async def undeclared():
    return {'ok': True}


@router.post(
    '/body', dependencies=[Depends(requires('test_mw:PostBody', legacy=Legacy.ADMIN))]
)
async def body(payload: dict):
    return payload


@pytest.fixture
def authorizer():
    return ScriptedAuthorizer(
        lambda principal, action, resource: action != 'test_mw:DeleteThing'
        and (action in ('test_mw:Open',) or not principal.is_anonymous)
    )


def make_client(authorizer, **kwargs):
    app = FastAPI()
    app.include_router(router, prefix='/svc')
    app.add_middleware(
        AuthzMiddleware,
        provider=AuthzProvider(HeaderAuthenticator(), authorizer),
        render_error=render,
        **kwargs,
    )
    return TestClient(app)


OK = {'Authorization': 'Bearer ok'}
BAD = {'Authorization': 'Bearer bad'}


def test_public_route_is_not_authenticated(authorizer):
    client = make_client(authorizer)
    HeaderAuthenticator.calls = 0
    # Even bad credentials are ignored on a public route, as before.
    assert client.get('/svc/health', headers=BAD).status_code == 200
    assert HeaderAuthenticator.calls == 0
    assert authorizer.calls == []


def test_missing_credentials(authorizer):
    response = make_client(authorizer).get('/svc/things/1')
    assert response.status_code == 401
    assert response.json() == {'error': 'Token missing in request'}


def test_failed_credentials_use_the_authenticators_error(authorizer):
    response = make_client(authorizer).get('/svc/things/1', headers=BAD)
    assert response.status_code == 401
    assert response.json() == {'error': 'Invalid session'}


def test_allowed_request_sees_principal_and_resource(authorizer):
    response = make_client(authorizer).get('/svc/things/42', headers=OK)
    assert response.status_code == 200
    assert response.json() == {
        'thing': '42',
        'principal': 'alice',
        'contextvar': 'alice',
    }
    [(principal, action, resource)] = authorizer.calls
    assert (principal, action, str(resource)) == (ALICE, 'test_mw:GetThing', 'thing/42')


def test_denial_uses_the_routes_status_and_message(authorizer):
    response = make_client(authorizer).delete('/svc/things/1', headers=OK)
    assert response.status_code == 401
    assert response.json() == {'error': 'Access denied'}


def test_denial_precedes_body_validation(authorizer):
    # The old checks ran in middleware, before FastAPI parsed the body.
    response = make_client(ScriptedAuthorizer(lambda *a: False)).post(
        '/svc/body', headers=OK, content=b'not json'
    )
    assert response.status_code == 403


def test_public_action_runs_as_anonymous(authorizer):
    response = make_client(authorizer).post('/svc/open')
    assert response.status_code == 200
    assert response.json() == {'anonymous': True}


def test_in_handler_checks(authorizer):
    response = make_client(authorizer).get('/svc/scoped', headers=OK)
    assert response.json() == {'all': True}
    assert authorizer.actions == ['test_mw:Scoped', 'test_mw:GetThing']


def test_undeclared_and_unknown_routes_need_authentication(authorizer):
    client = make_client(authorizer)
    assert client.get('/svc/undeclared').status_code == 401
    assert client.get('/svc/nowhere').status_code == 401
    assert client.get('/svc/nowhere', headers=OK).status_code == 404


def test_services_can_leave_unknown_paths_unauthenticated(authorizer):
    client = make_client(authorizer, authenticate_undeclared=False)
    assert client.get('/svc/nowhere').status_code == 404


def test_wrong_method_on_a_public_path_is_a_405(authorizer):
    assert make_client(authorizer).post('/svc/health').status_code == 405


def test_public_paths(authorizer):
    client = make_client(authorizer, public_paths=('/svc/undeclared',))
    assert client.get('/svc/undeclared').status_code == 200


def test_options_requests_pass_through(authorizer):
    assert make_client(authorizer).options('/svc/things/1').status_code == 405


def test_dependency_enforces_without_middleware():
    """A route served without the middleware (a websocket, a bare test app)."""
    app = FastAPI()
    app.include_router(router)
    install(
        AuthzProvider(HeaderAuthenticator(), ScriptedAuthorizer({'test_mw:GetThing'}))
    )
    try:
        client = TestClient(app)
        assert client.get('/things/1').status_code == 401
        assert client.get('/things/1', headers=OK).status_code == 200
        assert client.delete('/things/1', headers=OK).status_code == 401
        assert client.get('/health').status_code == 200
    finally:
        install(None)


def test_websocket_routes_are_authorized_by_their_dependency():
    ws_router = APIRouter()

    @ws_router.websocket(
        '/stream',
        dependencies=[Depends(requires('test_mw:Stream', legacy=Legacy.AUTHENTICATED))],
    )
    async def stream(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_text('hi')
        await websocket.close()

    app = FastAPI()
    app.include_router(ws_router, prefix='/ws')
    install(
        AuthzProvider(HeaderAuthenticator(), ScriptedAuthorizer({'test_mw:Stream'}))
    )
    try:
        client = TestClient(app)
        with client.websocket_connect('/ws/stream', headers=OK) as ws:
            assert ws.receive_text() == 'hi'
        with pytest.raises(Exception):
            with client.websocket_connect('/ws/stream') as ws:
                ws.receive_text()
    finally:
        install(None)


def test_principal_is_frozen():
    with pytest.raises(Exception):
        ALICE.id = 'mallory'  # type: ignore[misc]
    assert isinstance(ALICE, Principal)
    assert ALICE.user_id == 'alice'
