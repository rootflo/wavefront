"""Every inference_app route declares an action, and who may call it is unchanged.

Compares the routes, the action catalog and the access matrix (each route x
caller -> status) with the committed snapshot. Regenerate it on purpose, and
review the diff, with::

    AUTHZ_UPDATE_SNAPSHOT=1 pytest apps/inference_app/tests/test_inference_app_authz_snapshot.py
"""

from pathlib import Path

from flo_testing.authz import check_authz_snapshot

SNAPSHOT = Path(__file__).resolve().parents[1] / 'authz_snapshot.json'


def test_routes_and_access_match_snapshot():
    check_authz_snapshot(
        SNAPSHOT,
        'inference_app.router.catalog:build_app',
        '--allow-undeclared',
    )
