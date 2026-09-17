import re
import uuid
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator

# Matches agents/workflows: a name is a path-safe identifier, not free text.
NAME_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]*$')

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
    system_prompt: str = Field(..., description='System prompt sent on every turn')
    welcome_message: Optional[str] = Field(
        None,
        description=(
            'Greeting stored as the first assistant message of every new session'
        ),
    )
    llm_config_id: uuid.UUID = Field(..., description='LLM inference config ID')
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
