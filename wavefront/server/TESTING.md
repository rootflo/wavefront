# Testing

## Running

From `server/`:

```bash
pytest                         # everything
pytest -n auto --dist loadfile # everything, in parallel
pytest modules/auth_module     # one module
pytest -k "reset_password"     # by name
```

`APP_ENV=test` and `SUPERSET_FLAG=true` are set by the harness, so no env
prelude is needed. Both are read at import time -- `APP_ENV` decides whether the
embedding columns map to pgvector's `Vector` or to `Text`, and `SUPERSET_FLAG`
decides whether `AuthContainer` even defines `superset_service` -- so the
harness sets them on plugin import, before any module is imported. An explicit
value in your environment still wins.

Postgres has to be on `PATH` (`initdb`, `pg_ctl`). `brew install postgresql@14`
is enough; no server needs to be running and no database needs to exist.

Configuration lives in one place, `[tool.pytest.ini_options]` in
[`server/pyproject.toml`](pyproject.toml). Modules do not carry their own pytest
config.

## How the database fixtures work

The schema is expensive to build and identical for every test, so it is built
once per session into a template database, and each test clones it:

```
session:  start cluster (~1.4s)  ->  create_all, 57 tables (~0.3s)  ->  template
test:     CREATE DATABASE ... TEMPLATE  (~0.14s)  ->  drop afterwards
```

Postgres serves the clone as a file copy of an already-initialised directory.
Each test still gets a genuinely private database, so there is no
shared state to leak and no ordering dependency.

Under `-n auto` each xdist worker is its own pytest session, so it gets its own
cluster on its own port.

## Writing tests for a new module

Add the harness to the module's dev group:

```toml
[dependency-groups]
dev = [
    "flo-testing",
]

[tool.uv.sources]
flo-testing = { workspace = true }
```

That is all that is needed -- `flo-testing` registers as a pytest plugin, so
every fixture below is available without importing or copying anything.

The module's `tests/conftest.py` then only describes what is specific to it: its
own container, and its router.

```python
import pytest
from flo_testing import make_test_client
from my_module.controllers.thing_controller import thing_router
from my_module.my_container import MyContainer


@pytest.fixture
def setup_containers(core_containers):
    my_container = MyContainer()
    core_containers.wire(my_container, packages=['my_module.controllers'])
    core_containers.wire(
        core_containers.common, packages=['my_module.controllers']
    )
    return core_containers.auth, core_containers.common, my_container


@pytest.fixture
def test_client(setup_containers):
    return make_test_client(thing_router)
```

Always register containers through `core_containers.wire(...)` rather than
calling `container.wire(...)` directly: the harness tracks what it wired and
unwires all of it in teardown. Several conftests used to wire containers they
never unwired, which left `dependency_injector` overrides in place and made
failures depend on test order.

A test then looks like:

```python
async def test_list_things(test_client, seed_session, auth_headers):
    await seed_session()
    response = test_client.get('/floware/v1/things', headers=auth_headers)
    assert response.status_code == 200
```

## Fixtures

### Database

| Fixture             | Scope    | What it gives you                                |
| ------------------- | -------- | ------------------------------------------------ |
| `test_engine`       | function | Async engine on a private database for this test |
| `test_session`      | function | `async_sessionmaker` bound to it                 |
| `db_client`         | function | `StubDbClient`, what the repositories expect     |
| `postgres_cluster`  | session  | The cluster itself; rarely needed directly       |
| `postgres_template` | session  | Cluster URL, schema already built                |

### Identity

| Fixture                           | What it gives you                                              |
| --------------------------------- | -------------------------------------------------------------- |
| `test_user_id`, `test_session_id` | Fresh UUIDs for this test                                      |
| `auth_token`                      | Bearer token for that user                                     |
| `auth_headers`                    | `{'Authorization': 'Bearer ...'}`, ready to pass to the client |

### Containers

`core_containers` builds the four containers every API test needs -- db, common,
auth, user -- with the standard cache, token service and email stand-ins. It
exposes `.db_repo`, `.common`, `.auth`, `.user`, plus `.db_client`,
`.cache_manager`, `.token_service`, `.email_send_service`, `.user_id`,
`.session_id`, and the `.wire(...)` method described above.

`user_config` is the config `UserContainer` is built with. Override it in a
module conftest to change it.

### Seeding

`seed_session()` inserts the user and login session an authenticated request
needs. `seed_user_session(factory, user_id, session_id, **overrides)` is the
underlying function if you need to seed something other than the default user.

### Auth patching

`get_current_user` and `check_is_admin` are imported into each controller's own
namespace, so they must be patched _there_, not at their definition site -- and
often in two namespaces at once, because the read paths reach `check_is_admin`
through `user_utils.can_read_users` instead.

```python
@pytest.fixture
def as_admin(patch_auth):
    patch_auth('my_module.controllers.thing_controller')

@pytest.fixture
def as_non_admin(patch_auth):
    patch_auth('my_module.controllers.thing_controller', is_admin=False)
```

`patch_auth` patches both helpers. `patch_current_user` and `patch_is_admin`
patch one each, for tests that compose them -- a real-looking admin check with a
deliberately wrong `role_id`, say. All three also patch `user_utils` unless you
pass `include_user_utils=False`.

The real `user_utils.get_current_user` is sync and returns
`(role_id, user_id, session_id)` -- role first.

`patch_feature_flag(namespace, enabled)` forces `is_feature_enabled` on or off.

## Tests that do not need a database

Most tests should not. If a module's logic can be exercised against a fake
session, do that -- those tests run in milliseconds instead of ~0.15s, and they
are easier to read.
[`modules/chatbots_module/tests/fakes.py`](modules/chatbots_module/tests/fakes.py)
is the model to copy: a small `FakeDbSession` that records `add`/`flush`/
`commit`/`rollback` and emulates only flush-assigned primary keys.

Reach for the database fixtures when you are testing a real query, a constraint,
a cascade, or a transaction boundary.

## Conventions

- Do not add `tests/__init__.py`. Test directories are not packages; adding one
  makes two modules both claim the top-level name `tests` and breaks collection
  for the whole workspace.
- Do not `from conftest import X` or `from tests.conftest import X`. Which
  `conftest` that resolves to depends on import order across the workspace.
  Expose the thing as a fixture instead, or put it in a uniquely named helper
  module next to the tests.
- Helper modules in a test directory need repo-unique filenames (`fakes.py` is
  taken), since test directories share a flat import namespace.
- New models go in
  [`db_repo_module/models/__init__.py`](modules/db_repo_module/db_repo_module/models/__init__.py).
  That package is what guarantees `Base.metadata` is complete; a model missing
  from it breaks `create_all` on the first unresolved cross-module foreign key,
  and breaks Alembic autogenerate the same way.

## Known state

64 tests currently fail on `develop`. They are pre-existing failures unrelated
to the harness -- `plugins_module` fails 32 of 34 and
`common_module/test_odata_parser.py` fails 15 of 21 even when run alone -- and
they are tracked separately. CI cannot gate on green until they are fixed.
