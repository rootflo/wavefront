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

# Length of the auto-generated session title, derived from the first user
# message. Long enough to be recognisable in a sidebar, short enough to fit one.
TITLE_MAX_LENGTH = 60

ROLE_USER = 'user'
ROLE_ASSISTANT = 'assistant'
ROLE_SYSTEM = 'system'
