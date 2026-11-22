"""Chat tester: a small Streamlit app for exercising chatbot sessions by hand.

Not a product UI. It talks to a running floware over HTTP exactly as a client
would: log in, pick a chatbot, open or reopen a session, send messages, and
watch the reply arrive. For an agent-backed chatbot each tool call and result
is shown as it happens.

    cd wavefront/server/scripts/chat_tester
    uvx --with httpx streamlit run app.py
"""

import json
from datetime import datetime
from typing import Any, Iterator, Optional

import httpx
import streamlit as st

DEFAULT_SERVER = 'http://localhost:8001/floware'

# flo-ai stores a tool result with this lead-in, and a tool given prefilled
# parameters with this suffix on its name. Both are noise to someone reading
# the conversation, so they are trimmed for display only.
TOOL_RESULT_PREFIX = 'Here is the result of the tool call:'
PARTIAL_TOOL_SUFFIX = '_partial'


class SignedOut(Exception):
    """The server no longer accepts the stored token."""


# -- talking to floware ----------------------------------------------------


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=st.session_state.server,
        headers={'Authorization': f'Bearer {st.session_state.token}'},
        timeout=httpx.Timeout(300.0, connect=10.0),
    )


def _error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300] or f'HTTP {response.status_code}'
    meta = body.get('meta') or {}
    return str(meta.get('error') or body.get('detail') or body)[:300]


def api(method: str, path: str, **kwargs) -> dict[str, Any]:
    """Call floware and return the response's `data`, raising on failure."""
    with _client() as client:
        response = client.request(method, path, **kwargs)
    if response.status_code == 401:
        raise SignedOut(_error_text(response))
    if response.status_code >= 400:
        raise RuntimeError(f'{response.status_code}: {_error_text(response)}')
    return response.json().get('data') or {}


def sign_in(server: str, email: str, password: str) -> Optional[str]:
    """Log in. Returns an error message, or None on success."""
    try:
        response = httpx.post(
            f'{server}/v1/authenticate',
            json={'email': email, 'password': password},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        return f'Could not reach {server}: {exc}'

    if response.status_code != 200:
        return _error_text(response)

    user = (response.json().get('data') or {}).get('user') or {}
    if not user.get('access_token'):
        return 'The server accepted the login but returned no access token.'

    st.session_state.server = server
    st.session_state.token = user['access_token']
    st.session_state.email = email
    return None


def sign_out() -> None:
    for key in ('token', 'email', 'session_id', 'chatbot_id'):
        st.session_state.pop(key, None)


def stream_reply(session_id: str, content: str) -> Iterator[dict[str, Any]]:
    """Send a message and yield the reply's SSE frames as they arrive."""
    with _client() as client:
        with client.stream(
            'POST',
            f'/v1/chat-sessions/{session_id}/messages',
            params={'stream': 'true'},
            json={'content': content},
        ) as response:
            if response.status_code == 401:
                raise SignedOut('Your session has expired.')
            if response.status_code != 200:
                response.read()
                yield {'error': f'{response.status_code}: {_error_text(response)}'}
                return
            for line in response.iter_lines():
                if line.startswith('data: '):
                    yield json.loads(line[len('data: ') :])


# -- display helpers -------------------------------------------------------


def tool_label(name: Optional[str]) -> str:
    name = name or 'tool'
    return name.removesuffix(PARTIAL_TOOL_SUFFIX)


def tool_result_text(content: Optional[str]) -> str:
    text = (content or '').strip()
    if text.startswith(TOOL_RESULT_PREFIX):
        text = text[len(TOOL_RESULT_PREFIX) :].strip()
    return text


def when(timestamp: Optional[str]) -> str:
    if not timestamp:
        return ''
    try:
        return datetime.fromisoformat(timestamp).astimezone().strftime('%d %b %H:%M')
    except ValueError:
        return timestamp


def show_step(call: dict[str, Any], result: Optional[str]) -> None:
    """One tool call and what it returned."""
    arguments = json.dumps(call.get('arguments') or {}, ensure_ascii=False)
    with st.expander(f'🔧 {tool_label(call.get("name"))}  `{arguments}`'):
        if result is None:
            st.caption('No result was stored for this call.')
        else:
            st.code(tool_result_text(result), language=None)


def show_history(messages: list[dict[str, Any]], show_notices: bool) -> None:
    """Render stored rows as a conversation.

    A turn of an agent-backed chatbot is several rows: an assistant row per
    tool call, a tool row per result, then the reply. They are drawn as one
    assistant message, with the steps folded away above the text.
    """
    index = 0
    while index < len(messages):
        row = messages[index]
        metadata = row.get('metadata') or {}

        if metadata.get('notice'):
            if show_notices:
                st.caption(f'note to model ({row["role"]}): {row["content"]}')
            index += 1
            continue

        if row['role'] == 'user':
            with st.chat_message('user'):
                st.markdown(row['content'])
            index += 1
            continue

        # Everything up to the next user message belongs to one reply.
        with st.chat_message('assistant'):
            while index < len(messages) and messages[index]['role'] != 'user':
                row = messages[index]
                metadata = row.get('metadata') or {}
                calls = metadata.get('tool_calls')

                if metadata.get('notice'):
                    if show_notices:
                        st.caption(f'note to model ({row["role"]}): {row["content"]}')
                elif calls:
                    if row['content']:
                        st.markdown(row['content'])
                    following = (
                        messages[index + 1] if index + 1 < len(messages) else None
                    )
                    answered = following is not None and following['role'] == 'tool'
                    show_step(calls[0], following['content'] if answered else None)
                    if answered:
                        index += 1
                elif row['role'] == 'tool':
                    # A result whose call is not in view (an older page).
                    show_step({'name': metadata.get('name')}, row['content'])
                else:
                    st.markdown(row['content'])
                index += 1


def run_turn(session_id: str, content: str) -> bool:
    """Send `content` and draw the reply as it streams in.

    Returns False when the turn failed, so the caller can leave the error on
    screen instead of redrawing over it.
    """
    with st.chat_message('user'):
        st.markdown(content)

    with st.chat_message('assistant'):
        status = st.status('Thinking…', expanded=True)
        answer = st.empty()
        text = ''
        failed: Optional[str] = None
        steps = 0

        for frame in stream_reply(session_id, content):
            kind = frame.get('type')
            if kind == 'tool_call':
                steps += 1
                arguments = json.dumps(frame.get('arguments') or {}, ensure_ascii=False)
                status.update(label=f'Calling {tool_label(frame.get("name"))}…')
                status.write(f'🔧 **{tool_label(frame.get("name"))}** `{arguments}`')
            elif kind == 'tool_result':
                status.code(tool_result_text(frame.get('content')), language=None)
                status.update(label='Thinking…')
            elif kind == 'message':
                text = frame.get('content') or ''
                answer.markdown(text)
            elif kind == 'notice':
                status.caption(f'note to model: {frame.get("content")}')
            elif 'error' in frame:
                failed = str(frame['error'])
            elif 'content' in frame:
                # A prompt-based chatbot streams its reply as text deltas.
                text += frame['content']
                answer.markdown(text)

        if failed:
            status.update(label='Failed', state='error', expanded=True)
            st.error(failed)
        elif steps:
            status.update(
                label=f'Used {steps} tool call{"s" if steps != 1 else ""}',
                state='complete',
                expanded=False,
            )
        else:
            status.update(label='Replied', state='complete', expanded=False)
        return failed is None


# -- pages -----------------------------------------------------------------


def login_page() -> None:
    st.title('Chat tester')
    st.caption('Sign in to a running floware to chat with its chatbots.')

    with st.form('login'):
        server = st.text_input(
            'Server', value=st.session_state.get('server', DEFAULT_SERVER)
        )
        email = st.text_input('Email', value=st.session_state.get('email', ''))
        password = st.text_input('Password', type='password')
        submitted = st.form_submit_button('Sign in', type='primary')

    st.caption(
        'Careful with the password: floware locks an account after three '
        'failed attempts.'
    )

    if submitted:
        if not email or not password:
            st.error('Enter an email and a password.')
            return
        error = sign_in(server.rstrip('/'), email, password)
        if error:
            st.error(error)
        else:
            st.rerun()


def pick_chatbot() -> Optional[dict[str, Any]]:
    """The chatbot dropdown. Returns the chosen chatbot, or None."""
    try:
        chatbots = api('GET', '/v1/chatbots', params={'enabled': 'true'}).get(
            'chatbots', []
        )
    except RuntimeError as exc:
        # Listing chatbots is admin-only; anyone can still chat with one by id.
        st.sidebar.warning(f'Could not list chatbots ({exc}).')
        chatbot_id = st.sidebar.text_input('Chatbot id')
        return (
            {'id': chatbot_id, 'name': chatbot_id, 'agent_id': None}
            if chatbot_id
            else None
        )

    if not chatbots:
        st.sidebar.info('No enabled chatbots on this server.')
        return None

    def label(chatbot: dict[str, Any]) -> str:
        kind = 'agent' if chatbot.get('agent_id') else 'prompt'
        return f'{chatbot["name"]}  ·  {kind}'

    ids = [chatbot['id'] for chatbot in chatbots]
    by_id = {chatbot['id']: chatbot for chatbot in chatbots}
    current = st.session_state.get('chatbot_id')
    chosen = st.sidebar.selectbox(
        'Chatbot',
        ids,
        index=ids.index(current) if current in ids else 0,
        format_func=lambda chatbot_id: label(by_id[chatbot_id]),
    )
    if chosen != current:
        # Sessions belong to a chatbot, so the open one no longer applies.
        st.session_state.chatbot_id = chosen
        st.session_state.pop('session_id', None)
    return by_id[chosen]


def session_list(chatbot: dict[str, Any]) -> None:
    """New-chat button and this user's sessions with the chosen chatbot."""
    if st.sidebar.button('＋ New chat', width='stretch', type='primary'):
        created = api('POST', f'/v1/chatbots/{chatbot["id"]}/sessions', json={})
        st.session_state.session_id = created['session']['id']
        st.rerun()

    sessions = api(
        'GET', '/v1/chat-sessions', params={'chatbot_id': chatbot['id'], 'limit': 50}
    ).get('sessions', [])

    st.sidebar.caption(f'{len(sessions)} session{"s" if len(sessions) != 1 else ""}')
    for session in sessions:
        is_open = session['id'] == st.session_state.get('session_id')
        title = session.get('title') or 'New chat'
        if st.sidebar.button(
            f'{"● " if is_open else ""}{title[:40]}',
            key=f'open-{session["id"]}',
            help=when(session.get('created_at')),
            width='stretch',
        ):
            st.session_state.session_id = session['id']
            st.rerun()


def chat_page() -> None:
    st.sidebar.caption(f'{st.session_state.email}  \n{st.session_state.server}')
    if st.sidebar.button('Sign out'):
        sign_out()
        st.rerun()
    st.sidebar.divider()

    chatbot = pick_chatbot()
    if not chatbot:
        st.info('Choose a chatbot to start.')
        return

    session_list(chatbot)
    st.sidebar.divider()
    show_notices = st.sidebar.toggle('Show notes to the model', value=False)
    show_rows = st.sidebar.toggle('Show stored rows', value=False)

    kind = 'agent-backed' if chatbot.get('agent_id') else 'prompt-based'
    st.subheader(chatbot['name'])
    st.caption(f'{kind} chatbot')

    session_id = st.session_state.get('session_id')
    if not session_id:
        st.info('Start a new chat, or open one from the list on the left.')
        return

    messages = api(
        'GET', f'/v1/chat-sessions/{session_id}/messages', params={'limit': 200}
    ).get('messages', [])
    show_history(messages, show_notices)

    prompt = st.chat_input('Message')
    if prompt and run_turn(session_id, prompt):
        # Redraw from what the server stored, so the page shows the same thing
        # a reopened session would.
        st.rerun()

    if show_rows:
        with st.expander(f'Stored rows ({len(messages)})', expanded=True):
            st.dataframe(
                [
                    {
                        'role': row['role'],
                        'content': row['content'],
                        'metadata': json.dumps(row['metadata'])
                        if row['metadata']
                        else '',
                        'created_at': row['created_at'],
                    }
                    for row in messages
                ],
                width='stretch',
                hide_index=True,
            )


def main() -> None:
    st.set_page_config(page_title='Chat tester', page_icon='💬', layout='centered')
    if 'token' not in st.session_state:
        login_page()
        return
    try:
        chat_page()
    except SignedOut:
        sign_out()
        st.warning('Your session has expired. Sign in again.')
        login_page()
    except RuntimeError as exc:
        st.error(str(exc))
    except httpx.HTTPError as exc:
        st.error(f'Could not reach {st.session_state.server}: {exc}')


main()
