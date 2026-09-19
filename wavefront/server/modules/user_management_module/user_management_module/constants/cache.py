"""Cache key constants for the user directory.

Every key built here carries the same `{user_data}` hash tag. Redis Cluster
hashes only the substring between the first `{` and the `}` that follows it, so
the tag — not the rest of the key — decides which of the 16,384 slots a key
lands in. Sharing it puts the whole family on one slot, which is what lets
`invalidate_query` clear them with a single multi-key DEL; without it Redis
hashes each key independently and rejects the DEL with CROSSSLOT.

That means the tag and the pattern have to stay in lockstep with the builders,
hence this module: a new `user_data` key added elsewhere with a hand-written
prefix would be invisible to the invalidation and would serve stale reads until
its TTL ran out.
"""

import uuid
from typing import List, Optional, Union

# The literal braces are part of the key. They must appear before any
# interpolated value so that user-supplied text (a search term containing a
# brace, say) can never shift which substring Redis treats as the tag.
USER_DATA_TAG = '{user_data}'

# Matches every key built below. `{` and `}` are not glob metacharacters, so
# KEYS/SCAN compare them literally.
USER_DATA_PATTERN = f'{USER_DATA_TAG}_*'


def user_list_cache_key(
    offset: int,
    limit: int,
    search: Optional[str],
    roles: Optional[List[str]],
    include_roles: bool = True,
) -> str:
    """Key for one page of the user listing, per filter combination.

    `include_roles` is part of the key because the listing serves two different
    payloads from the same filters: admins get roles, groups and usernames,
    non-admins get a trimmed directory. Without it the two would collide on one
    entry and whichever call populated it first would serve its shape to the
    other — handing a non-admin the role membership the trimmed payload exists
    to withhold.
    """
    return f'{USER_DATA_TAG}_{offset}_{limit}_{search}_{roles}_{include_roles}'


def user_by_id_cache_key(user_id: str) -> str:
    """Key for a single user resolved by id."""
    return f'{USER_DATA_TAG}_id_{user_id}'


def get_session_cache_key(session_id: Union[str, uuid.UUID]) -> str:
    """Cache key for a live auth session."""
    return f'session_{str(session_id)}'


def password_reset_latest_key(user_id: str) -> str:
    """Pointer from a user to the reset code currently in force."""
    return f'pwreset_latest_{user_id}'
