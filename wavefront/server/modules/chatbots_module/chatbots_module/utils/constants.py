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
# One step of an agent's turn: the result a tool returned.
ROLE_TOOL = 'tool'

# How many stored rows are replayed to an agent-backed chatbot on each turn.
#
# Higher than MAX_HISTORY_MESSAGES because an agent turn is several rows (each
# tool call and each result is its own row), so the same number of exchanges
# takes more of them. The window is then moved forward to the start of a turn:
# see AgentChatService.to_agent_messages.
MAX_AGENT_HISTORY_MESSAGES = 200

# Shown to the caller when generation fails, on both the JSON and the SSE path.
#
# A single constant because the two paths must not drift, and because the
# underlying exception must never reach the client: it comes from the provider
# SDK, so it can carry the configured base_url (potentially an internal gateway
# host), deployment names, org identifiers, or an API-key prefix on an auth
# failure. Every chat route is open to any authenticated user, not just admins.
# The real error goes to the logs via logger.exception.
MODEL_FAILURE_MESSAGE = (
    'The model failed to respond. Your message was saved; please retry.'
)

# An agent-backed turn that policy or the provider declined. Nothing the agent
# did in that turn is kept; the user's message is.
BLOCKED_BY_POLICY_MESSAGE = 'This message was blocked by the content policy.'
MODEL_REFUSED_MESSAGE = 'The model declined to respond to this request.'

# A step of the agent's turn could not be written. The turn is stopped rather
# than continued with a hole in the stored conversation.
TURN_NOT_SAVED_MESSAGE = (
    'The reply could not be saved. Your message was saved; please retry.'
)

# The agent behind a chatbot was deleted, or the pinned version was.
AGENT_UNAVAILABLE_MESSAGE = (
    'The agent behind this chatbot is no longer available; '
    'the conversation is read-only'
)
