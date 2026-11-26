"""Lua scripts and constants for the generation-checked cache-aside protocol.

Plain get / fill / delete has a race once reads await: a reader loads
the old value from the source, a writer commits and deletes the key,
then the reader's late fill puts the old value back. NX fills don't help
(the key is absent after the delete). Instead every key K has a random
token in G(K):
  - a reader captures the token BEFORE loading the source, and fills only
    if the token is unchanged (atomic compare-and-set in Lua); a hit is
    valid only if the value carries the current token;
  - a writer first adds its id to W(K) (the set of active writers) and
    sets a *pending* marker as the token, strictly (Redis down:
    CacheUnavailableError, a 503, nothing changed). While a key is
    pending, reads bypass the cache and never fill it. After the change
    the writer removes its id from W(K); only the LAST writer to leave
    sets a fresh token, so one writer can't make a key cacheable while
    another is still mid-change. Set membership (not a counter) keeps a
    retried begin or end idempotent, and each attempt uses a new token, so
    a retry can never restore an older one. This step is best-effort: if it fails, the marker
    and W(K) expire (PENDING_TTL_SECONDS) and the next read creates a fresh
    token, so no fill from inside a change window can ever become valid.
    Writers never write the new value; the next read fills it.
A missing token never validates anything. If G(K) is missing while W(K)
still lists a writer (the marker alone was evicted), the read treats the
key as pending. K, G(K) and W(K) share a {hash tag} under the ``rt/`` prefix.
"""

TOKEN_TTL_SECONDS = 86400  # seconds; affects hit rate only, never correctness
# How long a key stays uncacheable if the post-change rotation fails. Must
# outlast the slowest write (a DB update plus a storage upload).
PENDING_TTL_SECONDS = 300
PENDING_MARKER = 'pending:'

# KEYS: value, generation, writers. ARGV: new token, generation TTL.
READ_SCRIPT = """
local token = redis.call('GET', KEYS[2])
if not token then
  if redis.call('SCARD', KEYS[3]) > 0 then
    return {'pending:lost', false}
  end
  token = ARGV[1]
  redis.call('SET', KEYS[2], token, 'EX', ARGV[2])
end
return {token, redis.call('GET', KEYS[1])}
"""

# KEYS: value, generation. ARGV: token, value, TTL.
FILL_SCRIPT = """
if string.sub(ARGV[1], 1, 8) == 'pending:' or redis.call('GET', KEYS[2]) ~= ARGV[1] then
  return 0
end
redis.call('SET', KEYS[1], ARGV[1] .. '\\n' .. ARGV[2], 'EX', ARGV[3])
return 1
"""

# KEYS: value, generation, writers. ARGV: pending marker, pending TTL, writer id.
BEGIN_CHANGE_SCRIPT = """
redis.call('SADD', KEYS[3], ARGV[3])
redis.call('EXPIRE', KEYS[3], ARGV[2])
redis.call('SET', KEYS[2], ARGV[1], 'EX', ARGV[2])
redis.call('DEL', KEYS[1])
return 1
"""

# KEYS: value, generation, writers. ARGV: fresh token, generation TTL, writer id.
# Returns 1 if this was the last writer (the key is cacheable again).
END_CHANGE_SCRIPT = """
redis.call('SREM', KEYS[3], ARGV[3])
redis.call('DEL', KEYS[1])
if redis.call('SCARD', KEYS[3]) > 0 then
  return 0
end
redis.call('SET', KEYS[2], ARGV[1], 'EX', ARGV[2])
return 1
"""
