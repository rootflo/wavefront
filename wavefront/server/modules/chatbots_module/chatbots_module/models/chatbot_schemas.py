import re
import uuid
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# A name is an identifier, not free text -- close to the agents/workflows rule
# in agents_module/utils/validation_utils.py, but requiring a leading letter
# rather than a letter or digit.
#
# Anchored with \Z, not $: Python's $ also matches just before a trailing
# newline, so `support-bot\n` would pass and be stored as a row distinct from
# `support-bot` while rendering identically in the console -- two chatbots that
# look the same and that the unique index cannot tell apart.
NAME_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]*\Z')

DEFAULT_NAMESPACE = 'default'


def _validate_name(value: str) -> str:
    if not NAME_PATTERN.match(value):
        raise ValueError(
            'name must start with a letter and contain only letters, '
            'digits, underscores and hyphens'
        )
    return value


def _validate_config(value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Reject a nonsensical temperature up front rather than letting the
    provider reject the whole turn later.

    Tests for key presence: 0 is valid and falsy.
    """
    if value is None:
        return value
    if 'temperature' in value:
        temperature = value['temperature']
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
            raise ValueError('config.temperature must be a number')
        if not 0 <= temperature <= 2:
            raise ValueError('config.temperature must be between 0 and 2')
    return value


class CreateChatbotPayload(BaseModel):
    name: str = Field(..., description='Unique name within the namespace')
    namespace: str = Field(
        DEFAULT_NAMESPACE, description='Namespace; auto-created if new'
    )
    description: Optional[str] = Field(None, description='Human-readable description')
    system_prompt: Optional[str] = Field(
        None,
        description='System prompt sent on every turn. Required unless agent_id is set',
    )
    welcome_message: Optional[str] = Field(
        None,
        description=(
            'Greeting stored as the first assistant message of every new session'
        ),
    )
    llm_config_id: Optional[uuid.UUID] = Field(
        None, description='LLM inference config ID. Required unless agent_id is set'
    )
    agent_id: Optional[uuid.UUID] = Field(
        None,
        description=(
            'Back the chatbot with this agent: its prompt, model and tools are '
            'used, and system_prompt and llm_config_id must be left out'
        ),
    )
    agent_version: Optional[int] = Field(
        None,
        ge=1,
        description="Pin an agent version; omitted follows the agent's current version",
    )
    config: Optional[Dict[str, Any]] = Field(
        None, description='Overrides on top of the LLM config; supports "temperature"'
    )
    enabled: bool = Field(
        False, description='Chatbots start disabled; enable once the prompt is ready'
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _validate_name(value)

    @field_validator('config')
    @classmethod
    def validate_config(cls, value):
        return _validate_config(value)

    @model_validator(mode='after')
    def validate_kind(self):
        """A chatbot is prompt-based or agent-backed, never a mix of the two."""
        if self.agent_id is not None:
            if self.system_prompt is not None or self.llm_config_id is not None:
                raise ValueError(
                    'an agent-backed chatbot takes its prompt and model from the '
                    'agent; leave out system_prompt and llm_config_id'
                )
            return self

        if self.agent_version is not None:
            raise ValueError('agent_version needs agent_id')
        if not self.system_prompt or not self.system_prompt.strip():
            raise ValueError('system_prompt is required unless agent_id is set')
        if self.llm_config_id is None:
            raise ValueError('llm_config_id is required unless agent_id is set')
        return self


class UpdateChatbotPayload(BaseModel):
    """Every field optional. `None` means "not supplied" rather than "set to
    null" -- the only nullable columns here (description, welcome_message,
    config) are cleared by sending an empty string / empty object instead, which
    keeps the payload free of a sentinel type.
    """

    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    welcome_message: Optional[str] = None
    llm_config_id: Optional[uuid.UUID] = None
    # A chatbot keeps the kind it was created as: agent_id and agent_version
    # apply to an agent-backed chatbot, system_prompt and llm_config_id to a
    # prompt-based one. The service rejects the other combination.
    agent_id: Optional[uuid.UUID] = None
    agent_version: Optional[int] = Field(None, ge=1)
    config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, value):
        return _validate_name(value) if value is not None else value

    @field_validator('config')
    @classmethod
    def validate_config(cls, value):
        return _validate_config(value)
