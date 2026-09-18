"""Cache key separation for the two user-listing payload shapes.

The listing serves admins a full directory row and everyone else a trimmed one.
Both shapes are cached, so the key has to tell them apart — otherwise whichever
caller populated the entry first would serve its shape to the other, handing a
non-admin the role membership the trimmed payload exists to withhold.

Pure key-building, so unlike the endpoint tests these need no database.
"""

import re

from user_management_module.constants.cache import (
    USER_DATA_PATTERN,
    user_list_cache_key,
)


class TestUserListCacheKey:
    def test_shapes_do_not_share_a_key(self):
        admin_key = user_list_cache_key(0, 100, None, None, include_roles=True)
        trimmed_key = user_list_cache_key(0, 100, None, None, include_roles=False)

        assert admin_key != trimmed_key

    def test_both_shapes_are_reachable_by_the_invalidation_pattern(self):
        """A key the pattern misses would serve stale reads until its TTL ran out."""
        pattern = re.compile(USER_DATA_PATTERN.replace('*', '.*'))

        for include_roles in (True, False):
            key = user_list_cache_key(0, 100, None, None, include_roles=include_roles)
            assert pattern.match(key), f'{key} is not matched by {USER_DATA_PATTERN}'

    def test_hash_tag_stays_at_the_front(self):
        """Redis Cluster hashes the first {...}; user input must not shift it."""
        key = user_list_cache_key(0, 100, 'search{with}braces', None)

        assert key.startswith('{user_data}')

    def test_filters_still_separate_keys(self):
        base = user_list_cache_key(0, 100, None, None)

        assert base != user_list_cache_key(10, 100, None, None)
        assert base != user_list_cache_key(0, 50, None, None)
        assert base != user_list_cache_key(0, 100, 'asha', None)
        assert base != user_list_cache_key(0, 100, None, ['admin'])

    def test_defaults_to_the_admin_shape(self):
        """Existing callers that omit the argument keep the full-payload key."""
        assert user_list_cache_key(0, 100, None, None) == user_list_cache_key(
            0, 100, None, None, include_roles=True
        )
