import asyncio
import uuid
from typing import Any, AsyncIterator, Optional

from common_module.log.logger import logger
from db_repo_module.models.chat_message import ChatMessage
from db_repo_module.models.chat_session import ChatSession
from db_repo_module.models.chatbot import Chatbot
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from flo_ai.agent import Agent, AgentEvent, AgentEventType
from flo_ai.llm.guarded_llm import GuardrailBlocked
from flo_ai.models import (
    AssistantMessage,
    BaseMessage,
    FunctionMessage,
    ModelRefusedError,
    ToolCall,
    UserMessage,
)

from chatbots_module.services.chat_session_service import ChatSessionService
from chatbots_module.utils.constants import (
    BLOCKED_BY_POLICY_MESSAGE,
    MAX_AGENT_HISTORY_MESSAGES,
    MODEL_FAILURE_MESSAGE,
    MODEL_REFUSED_MESSAGE,
    ROLE_ASSISTANT,
    ROLE_TOOL,
    ROLE_USER,
    TURN_NOT_SAVED_MESSAGE,
)

# Frame `type` values on the SSE stream of an agent-backed session.
FRAME_TOOL_CALL = 'tool_call'
FRAME_TOOL_RESULT = 'tool_result'
FRAME_MESSAGE = 'message'
FRAME_NOTICE = 'notice'


class AgentChatError(Exception):
    """The agent behind a chatbot could not be loaded or built."""


class AgentChatService:
    """Runs a chat turn for a chatbot that is backed by an agent.

    The counterpart of ChatInferenceService. That one makes a single model
    call; this one runs an agent, which may call tools several times before it
    replies. Each step of the turn is stored as its own `chat_messages` row as
    it happens, and passed back to the agent on the next turn, so the agent
    remembers what it did and not only what it said.

    The agents stack is injected rather than imported: this module does not
    depend on agents_module.
    """

    def __init__(
        self,
        chat_session_service: ChatSessionService,
        chat_message_repository: SQLAlchemyRepository[ChatMessage],
        agent_crud_service,
        agent_inference_service,
    ):
        self.chat_session_service = chat_session_service
        self.chat_message_repository = chat_message_repository
        self.agent_crud_service = agent_crud_service
        self.agent_inference_service = agent_inference_service
        # A turn outlives the request that started it when the client hangs
        # up, and asyncio keeps only weak references to tasks: without this
        # set, such a turn could be collected mid-run.
        self._turns: set[asyncio.Task] = set()

    # -- which sessions take this path ------------------------------------

    @staticmethod
    def is_agent_session(session: ChatSession) -> bool:
        """Decided from the session, not the chatbot.

        The session records what it was opened as, so a thread never changes
        kind part-way through whatever is later done to the chatbot.
        """
        return bool((session.metadata_ or {}).get('agent_id'))

    async def pin(self, chatbot: Chatbot) -> dict[str, Any]:
        """The agent and version a new session will run on, for its metadata.

        Resolved now, when the session opens: a chatbot that follows the
        agent's current version must not move a conversation onto a new
        version mid-thread, for the same reason a prompt-based session keeps
        a snapshot of its prompt.
        """
        try:
            agent = await self.agent_crud_service.get_agent(
                chatbot.agent_id, version=chatbot.agent_version
            )
        except ValueError as exc:
            raise AgentChatError(str(exc)) from exc

        return {
            'agent_id': str(chatbot.agent_id),
            'agent_version': agent['version'],
        }

    # -- building the agent -----------------------------------------------

    async def build_agent(
        self,
        session: ChatSession,
        access_token: Optional[str] = None,
        app_key: Optional[str] = None,
    ) -> Agent:
        """Build the session's agent, or raise AgentChatError.

        Separate from run_turn and called first, for the reason
        ChatInferenceService.resolve_llm is: once a streaming response has
        started, a failure can no longer choose a status code.

        `access_token` and `app_key` are the caller's own. The agent's tools
        act with them, so the chat cannot do what the user's account cannot.
        """
        pinned = session.metadata_ or {}
        try:
            agent_data = await self.agent_crud_service.get_agent(
                uuid.UUID(str(pinned['agent_id'])),
                version=pinned.get('agent_version'),
            )
            agent = await self.agent_inference_service.create_agent_from_yaml(
                agent_data['yaml_content'],
                agent_data['name'],
                access_token=access_token,
                app_key=app_key,
                namespace=agent_data['namespace'],
            )
        except Exception as exc:
            # Logged in full; the caller gets a fixed message, because what
            # went wrong here can name internal models, tools or endpoints.
            logger.exception(f'Could not build agent for chat session {session.id}')
            raise AgentChatError(
                f'Could not build the agent for session {session.id}'
            ) from exc

        # A person is on the other end: what they type is not a template, and
        # a question the agent asks is its reply.
        agent.interactive = True
        return agent

    # -- stored rows <-> agent messages -----------------------------------

    @staticmethod
    def to_agent_messages(rows: list[ChatMessage]) -> list[BaseMessage]:
        """Turn stored rows back into the conversation the agent is given.

        `rows` is a window of the newest rows, so it can open in the middle of
        a turn: on a tool result whose call was cut off, say. A provider
        rejects a request shaped like that, so the window is moved forward to
        the first user message.
        """
        start = next(
            (
                index
                for index, row in enumerate(rows)
                if row.role == ROLE_USER and not (row.metadata_ or {}).get('notice')
            ),
            len(rows),
        )

        messages: list[BaseMessage] = []
        for row in rows[start:]:
            metadata = row.metadata_ or {}
            if metadata.get('notice'):
                # The agent's notes to itself during an earlier turn. They
                # steered that turn and have no place in a later one.
                continue

            if row.role == ROLE_TOOL:
                messages.append(
                    FunctionMessage(
                        content=row.content,
                        name=metadata.get('name') or 'tool',
                        tool_call_id=metadata.get('tool_call_id'),
                    )
                )
            elif row.role == ROLE_USER:
                messages.append(UserMessage(content=row.content))
            else:
                calls = metadata.get('tool_calls')
                messages.append(
                    AssistantMessage(
                        content=row.content,
                        tool_calls=[
                            ToolCall(
                                name=call['name'],
                                arguments=call.get('arguments') or {},
                                id=call.get('id'),
                            )
                            for call in calls
                        ]
                        if calls
                        else None,
                    )
                )
        return messages

    @staticmethod
    def to_row(event: AgentEvent) -> tuple[str, str, Optional[dict[str, Any]]]:
        """(role, content, metadata) for the row that stores one agent step."""
        message = event.message
        content = getattr(message.content, 'text', message.content)
        content = '' if content is None else str(content)

        if event.type == AgentEventType.TOOL_CALL:
            return (
                ROLE_ASSISTANT,
                content,
                {
                    'tool_calls': [
                        {'id': call.id, 'name': call.name, 'arguments': call.arguments}
                        for call in message.tool_calls or []
                    ]
                },
            )

        if event.type == AgentEventType.TOOL_RESULT:
            return (
                ROLE_TOOL,
                content,
                {'name': message.name, 'tool_call_id': message.tool_call_id},
            )

        if event.type == AgentEventType.MESSAGE and event.is_final:
            return ROLE_ASSISTANT, content, None

        # A note the agent wrote to itself, or reasoning it was told to
        # continue from. Stored so the turn can be inspected; marked so it is
        # neither shown as a reply nor replayed.
        role = ROLE_USER if message.role == ROLE_USER else ROLE_ASSISTANT
        return role, content, {'notice': True}

    @staticmethod
    def to_frame(event: AgentEvent, row: ChatMessage) -> dict[str, Any]:
        """The SSE frame that tells the client about one stored step."""
        message = event.message
        frame: dict[str, Any] = {'message_id': str(row.id)}

        if event.type == AgentEventType.TOOL_CALL:
            call = (message.tool_calls or [None])[0]
            frame.update(
                type=FRAME_TOOL_CALL,
                name=call.name if call else None,
                arguments=call.arguments if call else {},
                content=row.content,
            )
        elif event.type == AgentEventType.TOOL_RESULT:
            frame.update(type=FRAME_TOOL_RESULT, name=message.name, content=row.content)
        elif event.type == AgentEventType.MESSAGE and event.is_final:
            frame.update(type=FRAME_MESSAGE, content=row.content, final=True)
        else:
            frame.update(type=FRAME_NOTICE, content=row.content)
        return frame

    # -- running a turn ---------------------------------------------------

    async def load_history(self, session_id: uuid.UUID) -> list[BaseMessage]:
        rows = await self.chat_session_service.get_history(
            session_id, limit=MAX_AGENT_HISTORY_MESSAGES
        )
        return self.to_agent_messages(rows)

    async def run_turn(
        self, agent: Agent, session: ChatSession, history: list[BaseMessage]
    ) -> AsyncIterator[dict[str, Any]]:
        """Run one turn, yielding a frame per step and a closing frame.

        `history` ends with the user's new message, already stored.

        Step frames carry a `type` (see to_frame). The closing frame is
        `{'done': True, 'message_id': ...}` or `{'error': ...}`.

        The agent runs in its own task and this generator only relays what it
        reports. If the client hangs up, the generator stops and the task
        carries on: the remaining steps are still stored, so the turn is whole
        when the user comes back. Stopping it part-way would leave a
        half-finished turn and throw away tool calls that already ran.
        """
        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(self._drive(agent, session, history, queue))
        self._turns.add(task)
        task.add_done_callback(self._turns.discard)

        while True:
            frame, is_last = await queue.get()
            yield frame
            if is_last:
                return

    async def _drive(
        self,
        agent: Agent,
        session: ChatSession,
        history: list[BaseMessage],
        queue: asyncio.Queue,
    ) -> None:
        """Run the agent, store each step, and always put a closing frame."""
        written: list[uuid.UUID] = []
        final_message_id: Optional[str] = None
        save_failed = False

        async def on_event(event: AgentEvent) -> None:
            nonlocal final_message_id, save_failed
            if save_failed:
                return

            role, content, metadata = self.to_row(event)
            try:
                row = await self.chat_session_service.add_message(
                    session_id=session.id,
                    role=role,
                    content=content,
                    metadata=metadata,
                )
            except Exception:
                # flo-ai logs a failing callback and lets the agent continue.
                # A stored conversation with a step missing cannot be replayed
                # (a tool result without its call, say), so the turn is stopped
                # here instead.
                logger.exception(
                    f'Could not store agent step for chat session {session.id}'
                )
                save_failed = True
                turn.cancel()
                # Give the cancellation somewhere to land now. Without this it
                # waits for the agent's next suspension, which is inside its
                # next model call.
                await asyncio.sleep(0)
                return

            written.append(row.id)
            if event.type == AgentEventType.MESSAGE and event.is_final:
                final_message_id = str(row.id)
            await queue.put((self.to_frame(event, row), False))

        turn = asyncio.ensure_future(agent.run(history, on_event=on_event))
        closing: dict[str, Any]
        try:
            await turn
        except asyncio.CancelledError:
            if not save_failed:
                # Cancelled from outside (shutdown): nothing left to report to.
                raise
            closing = {'error': TURN_NOT_SAVED_MESSAGE}
        except GuardrailBlocked:
            # Nothing the agent did in a blocked turn is kept, matching what
            # the agent does to its own history. The user's message stays.
            await self._discard(session, written)
            closing = {'error': BLOCKED_BY_POLICY_MESSAGE}
        except ModelRefusedError:
            await self._discard(session, written)
            closing = {'error': MODEL_REFUSED_MESSAGE}
        except Exception:
            # The exception stays in the logs: see MODEL_FAILURE_MESSAGE. The
            # steps stored so far are kept; flo-ai records a failed tool as the
            # result of its call, so they are still a valid conversation.
            logger.exception(f'Agent turn failed for chat session {session.id}')
            closing = {'error': MODEL_FAILURE_MESSAGE}
        else:
            closing = (
                {'error': TURN_NOT_SAVED_MESSAGE}
                if save_failed
                else {'done': True, 'message_id': final_message_id}
            )

        await queue.put((closing, True))

    async def _discard(self, session: ChatSession, row_ids: list[uuid.UUID]) -> None:
        """Remove the rows a declined turn wrote."""
        for row_id in row_ids:
            try:
                await self.chat_message_repository.delete_all(id=row_id)
            except Exception:
                logger.exception(
                    f'Could not remove step {row_id} of a declined turn in '
                    f'chat session {session.id}'
                )
