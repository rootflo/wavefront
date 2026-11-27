# authz-module

The authentication and authorization layer shared by every wavefront service.

- **`Principal`** — the one identity type a request runs as.
- **`requires(action, ...)` / `public_route`** — every route declares the action it
  performs, or that it is public. `authz lint-routes` fails CI for a route that
  does neither.
- **`Authenticator` / `Authorizer`** — the pluggable pair that turns a request
  into a principal and decides whether that principal may perform an action.
  `AUTHZ_PROVIDER` selects the implementation; the default reproduces each
  service's built-in rules, recorded on every action as its *legacy rule*.
- **Hooks** — `filter_capabilities`, `authorize_call`, `before_query` and
  `record`, called from the agent runtime, the datasource query path and after
  every decision. They are no-ops in the default provider.

## Declaring actions

```python
from authz_module import Legacy, from_path, public_route, requires

@router.put('/v1/agents/{agent_id}')
async def update_agent(
    agent_id: str,
    principal: Principal = Depends(
        requires('agents:UpdateAgent', resource=from_path('agent', 'agent_id'),
                 legacy=Legacy.ADMIN)
    ),
): ...

@router.get('/v1/health', dependencies=[Depends(public_route)])
async def health(): ...
```

Action names are `<service>:<Verb><Noun>`. Read verbs are `Get`, `List`,
`Describe`; writes `Create`, `Update`, `Delete`; execution `Invoke`, `Run`,
`Query`. One action per distinct permission, never per HTTP method or URL.

A check that depends on the request (an admin sees every row, everyone else
their own) is its own action, declared with `define_action` and checked with
`await is_allowed(request, 'users:ListAllUsers')`.

## Providers

`AUTHZ_PROVIDER` names an entry point in the `wavefront.authz` group. Its value is
a factory `(service: str, default: AuthzProvider) -> AuthzProvider`, so a
provider can keep the service's default authenticator and replace only the
authorizer. An unknown name fails at startup rather than falling back.

## CLI

```bash
authz export-catalog floware.router.catalog:routers   # every action as JSON
authz lint-routes floware.router.catalog:routers      # fails on unannotated routes
```
