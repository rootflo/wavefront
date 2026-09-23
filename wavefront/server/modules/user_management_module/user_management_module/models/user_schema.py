import re
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel
from pydantic import EmailStr
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

# bcrypt truncates beyond 72 bytes; bound inputs to avoid DoS via huge passwords.
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 72
PASSWORD_REGEX = (
    rf'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]'
    rf'{{{PASSWORD_MIN_LENGTH},{PASSWORD_MAX_LENGTH}}}$'
)

EMAIL_MAX_LENGTH = 254
NAME_MAX_LENGTH = 50
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 50
TOKEN_MAX_LENGTH = 4096
ID_LIST_MAX_ITEMS = 100
ROLE_ID_MAX_LENGTH = 100


def _validate_email_value(v: str) -> str:
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
        raise ValueError('Invalid email format')
    if '..' in v:
        raise ValueError('Email cannot contain consecutive dots')
    domain = v.split('@')[1]
    if len(domain.split('.')) < 2:
        raise ValueError('Invalid email domain')
    if len(domain) > 255:
        raise ValueError('Email domain too long')
    tld = domain.split('.')[-1]
    if not 2 <= len(tld) <= 63:
        raise ValueError('Invalid TLD length')
    return v.lower()


def _validate_password_strength(v: str) -> str:
    # bcrypt operates on UTF-8 bytes and truncates/errors past 72 bytes.
    # Field max_length only counts characters, so enforce the byte bound here
    # before the character-class regex (shared by NewUser, UpdateUser, ResetUser).
    if len(v.encode('utf-8')) > PASSWORD_MAX_LENGTH:
        raise ValueError(
            f'Password must be at most {PASSWORD_MAX_LENGTH} bytes when UTF-8 encoded'
        )
    if not re.match(PASSWORD_REGEX, v):
        raise ValueError(
            'Password must contain at least one uppercase letter, one lowercase letter, '
            'one number, and one special character'
        )
    return v


def _validate_name_value(v: Optional[str]) -> Optional[str]:
    if v is not None:
        # Letters required; spaces, apostrophes, and hyphens are also allowed
        # (e.g. Mary Jane, O'Brien, Mary-Jane). Length/blank rules stay on Field.
        cleaned = v.replace(' ', '').replace("'", '').replace('-', '')
        if not cleaned or not cleaned.isalpha():
            raise ValueError(
                'Name should only contain letters, spaces, apostrophes, and hyphens'
            )
    return v


def _validate_uuid_string(v: str, label: str = 'id') -> str:
    try:
        UUID(str(v))
    except ValueError as exc:
        raise ValueError(f'Invalid {label}: {v}') from exc
    return str(v)


def _validate_id_list(
    values: Optional[List[str]],
    *,
    label: str,
    require_uuid: bool = False,
) -> Optional[List[str]]:
    if values is None:
        return values
    if len(values) > ID_LIST_MAX_ITEMS:
        raise ValueError(f'{label} cannot contain more than {ID_LIST_MAX_ITEMS} items')
    if len(set(values)) != len(values):
        raise ValueError(f'{label} must be unique')
    for item in values:
        if not item or not str(item).strip():
            raise ValueError(f'{label} entries must be non-empty')
        if len(str(item)) > ROLE_ID_MAX_LENGTH:
            raise ValueError(
                f'{label} entries must be at most {ROLE_ID_MAX_LENGTH} characters'
            )
        if require_uuid:
            _validate_uuid_string(item, label.rstrip('s'))
    return values


class NewUser(BaseModel):
    email: EmailStr = Field(..., max_length=EMAIL_MAX_LENGTH)
    username: Optional[str] = Field(
        None, min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH
    )
    password: str = Field(
        ..., min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )
    confirm_password: str = Field(
        ..., min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )
    first_name: Optional[str] = Field(None, min_length=1, max_length=NAME_MAX_LENGTH)
    last_name: Optional[str] = Field(None, max_length=NAME_MAX_LENGTH)
    team_id: Optional[str] = Field(None, max_length=ROLE_ID_MAX_LENGTH)
    # Roles may be empty when the user draws their access from groups instead.
    # Console access is still mandatory and is validated in the controller over
    # direct roles and group roles together.
    role_id: List[str] = Field(default_factory=list, max_length=ID_LIST_MAX_ITEMS)
    group_ids: List[str] = Field(default_factory=list, max_length=ID_LIST_MAX_ITEMS)

    @field_validator('role_id')
    @classmethod
    def validate_role_ids(cls, v):
        return _validate_id_list(v, label='Role IDs')

    @field_validator('group_ids')
    @classmethod
    def validate_group_ids(cls, v):
        return _validate_id_list(v, label='Group IDs', require_uuid=True)

    @field_validator('team_id')
    @classmethod
    def validate_team_id(cls, v):
        if v is None:
            return v
        return _validate_uuid_string(v, 'team_id')

    @field_validator('email')
    @classmethod
    def validate_email_format(cls, v):
        return _validate_email_value(v)

    @field_validator('username')
    @classmethod
    def validate_username_format(cls, v):
        if v is None:
            return v
        if not re.match(r'^[a-zA-Z0-9._@+-]+$', v):
            raise ValueError(
                'Username may only contain letters, digits, and the characters . _ @ + -'
            )
        return v.lower()

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v):
        return _validate_password_strength(v)

    @field_validator('first_name', 'last_name')
    @classmethod
    def validate_name_format(cls, v):
        return _validate_name_value(v)

    @model_validator(mode='after')
    def validate_passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError('Password and confirm password do not match')
        return self


class UpdateUser(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=ROLE_ID_MAX_LENGTH)
    add_role_ids: Optional[List[str]] = Field(None, max_length=ID_LIST_MAX_ITEMS)
    delete_role_ids: Optional[List[str]] = Field(None, max_length=ID_LIST_MAX_ITEMS)
    add_group_ids: Optional[List[str]] = Field(None, max_length=ID_LIST_MAX_ITEMS)
    delete_group_ids: Optional[List[str]] = Field(None, max_length=ID_LIST_MAX_ITEMS)
    email: Optional[EmailStr] = Field(None, max_length=EMAIL_MAX_LENGTH)
    username: Optional[str] = Field(
        None, min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH
    )
    password: Optional[str] = Field(
        None, min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )
    confirm_password: Optional[str] = Field(
        None, min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )
    first_name: Optional[str] = Field(None, min_length=1, max_length=NAME_MAX_LENGTH)
    last_name: Optional[str] = Field(None, max_length=NAME_MAX_LENGTH)

    @field_validator('user_id')
    @classmethod
    def validate_user_id(cls, v):
        return _validate_uuid_string(v, 'user_id')

    @field_validator('add_role_ids', 'delete_role_ids')
    @classmethod
    def validate_role_ids(cls, v):
        return _validate_id_list(v, label='Role IDs')

    @field_validator('add_group_ids', 'delete_group_ids')
    @classmethod
    def validate_group_ids(cls, v):
        return _validate_id_list(v, label='Group IDs', require_uuid=True)

    @field_validator('email')
    @classmethod
    def validate_email_format(cls, v):
        if v is None:
            return v
        return _validate_email_value(v)

    @field_validator('username')
    @classmethod
    def validate_username_format(cls, v):
        if v is None:
            return v
        if not re.match(r'^[a-zA-Z0-9._@+-]+$', v):
            raise ValueError(
                'Username may only contain letters, digits, and the characters . _ @ + -'
            )
        return v.lower()

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v):
        if v is None:
            return v
        return _validate_password_strength(v)

    @field_validator('first_name', 'last_name')
    @classmethod
    def validate_name_format(cls, v):
        return _validate_name_value(v)

    @model_validator(mode='after')
    def validate_passwords_match(self):
        if self.password is not None or self.confirm_password is not None:
            if self.password != self.confirm_password:
                raise ValueError('Password and confirm password do not match')
        return self


class ResetUser(BaseModel):
    secret_token: str = Field(..., min_length=1, max_length=TOKEN_MAX_LENGTH)
    new_password: str = Field(
        ..., min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )
    confirm_password: str = Field(
        ..., min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )
    recaptcha_token: Optional[str] = Field(None, max_length=TOKEN_MAX_LENGTH)

    @field_validator('new_password')
    @classmethod
    def validate_password_strength(cls, v):
        return _validate_password_strength(v)

    @model_validator(mode='after')
    def validate_passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError('Password and confirm password do not match')
        return self


class SendResetPasswordEmailRequest(BaseModel):
    email: EmailStr = Field(..., max_length=EMAIL_MAX_LENGTH)
    recaptcha_token: Optional[str] = Field(None, max_length=TOKEN_MAX_LENGTH)
