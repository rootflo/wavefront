"""A chatbot's system prompt is admin-only.

Every route on chatbot_router is admin-gated, so the only way the prompt could
reach a normal user is through a session response -- `system_prompt_snapshot` is
a verbatim copy of it. The projection below is what keeps that from happening,
so it is worth a test that fails loudly if someone returns `to_dict()` directly.
"""

import uuid
from datetime import datetime, timezone

from db_repo_module.models.chat_session import ChatSession

from chatbots_module.controllers.chat_session_controller import _session_dict


def _session():
    now = datetime.now(timezone.utc)
    return ChatSession(
        id=uuid.uuid4(),
        chatbot_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title='A thread',
        system_prompt_snapshot='SECRET internal instructions',
        metadata_=None,
        is_deleted=False,
        created_at=now,
        updated_at=now,
    )


def test_snapshot_is_absent_from_the_response():
    payload = _session_dict(_session())

    assert 'system_prompt_snapshot' not in payload
    assert 'SECRET internal instructions' not in str(payload)


def test_the_rest_of_the_session_survives():
    session = _session()

    payload = _session_dict(session)

    assert payload['id'] == str(session.id)
    assert payload['chatbot_id'] == str(session.chatbot_id)
    assert payload['title'] == 'A thread'
    assert payload['is_deleted'] is False


def test_model_to_dict_still_carries_it_for_internal_use():
    # The projection is the boundary, not the model -- services legitimately
    # need the snapshot to build the prompt.
    assert _session().to_dict()['system_prompt_snapshot'] == (
        'SECRET internal instructions'
    )
