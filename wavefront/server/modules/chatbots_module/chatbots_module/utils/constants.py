"""Tunables for chat inference."""

# How many stored messages (not counting the system prompt) are replayed to the
# LLM on each turn.
#
# A flat count, not a token budget: crude, but predictable and cheap to reason
# about. A long thread silently drops its oldest turns rather than failing with
# a context-length error from the provider. Replacing this with a token-aware
# trim is the eventual fix -- it needs a tokenizer per provider, which is why it
# is not here yet.
MAX_HISTORY_MESSAGES = 50

# Longest single user message accepted, in characters (~8k tokens).
#
# Generous enough for a pasted document excerpt, bounded so an unbounded body
# cannot be written to a Text column and then rejected by the provider -- the
# insert and the round trip are both paid for before that rejection arrives.
#
# This bounds one turn, NOT the whole request: MAX_HISTORY_MESSAGES turns of
# this length together exceed every provider's context window, and that case
# still surfaces as a provider error (HTTP 502). Bounding the request properly
# needs a per-provider token count, which is the same missing piece as above.
MAX_MESSAGE_LENGTH = 32000

# Length of the auto-generated session title, derived from the first user
# message. Long enough to be recognisable in a sidebar, short enough to fit one.
TITLE_MAX_LENGTH = 60

ROLE_USER = 'user'
ROLE_ASSISTANT = 'assistant'
ROLE_SYSTEM = 'system'
