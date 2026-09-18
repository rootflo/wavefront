from typing import Optional

from pydantic import BaseModel, Field, field_validator

from chatbots_module.utils.constants import MAX_MESSAGE_LENGTH


class CreateChatSessionPayload(BaseModel):
    title: Optional[str] = Field(
        None,
        description='Optional title; otherwise derived from the first user message',
    )


class UpdateChatSessionPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


class SendMessagePayload(BaseModel):
    # Bounded at the API boundary so an oversized turn is rejected before it is
    # written to a Text column and then refused by the provider -- both the
    # insert and the round trip are paid for before that refusal arrives.
    content: str = Field(
        ...,
        max_length=MAX_MESSAGE_LENGTH,
        description=f'The user message (max {MAX_MESSAGE_LENGTH} characters)',
    )

    @field_validator('content')
    @classmethod
    def validate_content(cls, value: str) -> str:
        # A whitespace-only turn would be persisted and sent to the model as an
        # empty user message, which wastes a call and corrupts the thread.
        if not value.strip():
            raise ValueError('content must not be empty')
        return value
