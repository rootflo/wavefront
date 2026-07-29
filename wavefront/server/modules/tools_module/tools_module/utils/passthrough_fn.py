"""Re-emit an earlier node's output as this node's output.

A workflow returns the output of whichever node ran last, so any node that has to
run at the end for its side effect — writing to a datasource, calling an external
service — becomes the workflow's answer, replacing whatever the caller actually
wanted. This node runs after it and puts the real result back:

    - name: final_result
      function_name: passthrough
      input_filter: [quote_generator]   # whose output to re-emit

Being a function node it makes no model call, so the value is never re-derived or
re-typed on the way through.

``input_list`` is supplied by the function-node adapter: every message the node's
``input_filter`` selected, parsed, in execution order. Selecting exactly one node
therefore makes this an identity function on that node's output. Selecting several
re-emits the last of them.
"""

import json
from typing import Any, List, Optional


async def passthrough(input_list: Optional[List[Any]] = None) -> str:
    """Return the last selected upstream payload, unchanged.

    The payload has already been parsed from JSON by the adapter, so it is
    re-serialised on the way out. That round-trip preserves content and types
    exactly; only insignificant formatting (key order is kept, whitespace is not)
    can differ from the upstream node's own rendering.
    """
    if not input_list:
        return ''

    payload = input_list[-1]
    if isinstance(payload, str):
        return payload
    return json.dumps(payload)
