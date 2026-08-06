import json
import os
from urllib.parse import quote

import httpx

FLOWARE_BASE_URL = os.getenv('FLOWARE_BASE_URL', 'http://localhost:8001').rstrip('/')


async def fetch_configuration(namespace: str, key: str) -> str:
    """Fetch a stored configuration document via wavefront's own REST API
    (GET /v1/configurations/{namespace}/{key}).

    Configurations hold static reference data a deterministic step needs at
    execution time — thresholds, limits, lookup tables. Wavefront
    does not interpret the document; whatever was stored is what comes back.

    One config per node, addressed by namespace and key. To use several, add
    several nodes: the dependency is then visible in the graph and in the
    consuming node's `input_filter`, rather than hidden in prefilled params.

        - name: fetch_thresholds
          function_name: fetch_configuration
          prefilled_params:
            namespace: acme-dev
            key: thresholds

    A message processor cannot fetch this itself — the JS runtime is sandboxed
    with a short script timeout and no outbound access. It reads the document
    from `node_outputs`, having selected this node in its `input_filter`:

        const limits = (input.node_outputs || {})['fetch_thresholds'][0];

    Returns the document as a JSON string. Unlike the datasource tools, which
    return a human-readable confirmation, this node's output is *data for a
    downstream node*: the function-node adapter parses each input as JSON and
    only records `node_outputs` for payloads it could parse, so a prose return
    value would be dropped or would fail the consuming node outright.
    """
    url = (
        f'{FLOWARE_BASE_URL}/floware/v1/configurations/'
        f'{quote(namespace, safe="")}/{quote(key, safe="")}'
    )
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
        except httpx.RequestError as e:
            raise Exception(
                f"Failed to reach configuration API for '{namespace}/{key}': {e}"
            )

    # Raised rather than returned as a message: a missing config means the
    # calculation downstream would run on nothing. Failing here names the
    # namespace and key; returning prose would surface as an unrelated JSON
    # error in whichever node consumed it.
    if response.status_code == 404:
        raise Exception(f"Configuration '{key}' not found in namespace '{namespace}'")
    if response.status_code != 200:
        raise Exception(
            f"Failed to fetch configuration '{namespace}/{key}' "
            f'({response.status_code}): {response.text}'
        )

    try:
        body = response.json()
    except json.JSONDecodeError:
        raise Exception(
            f"Configuration API returned non-JSON for '{namespace}/{key}': "
            f'{response.text}'
        )

    return json.dumps(body.get('data'))
