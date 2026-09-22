import re
from typing import List, Optional

from pydantic import BaseModel
from pydantic import EmailStr
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

PASSWORD_REGEX = r'^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$'


class NewUser(BaseModel):
    email: EmailStr = Field(..., max_length=254)  # RFC 5321 standard max length
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, max_length=50)
    team_id: Optional[str] = None
    # Roles may be empty when the user draws their access from groups instead.
    # Console access is still mandatory and is validated in the controller over
    # direct roles and group roles together.
    role_id: List[str] = Field(default_factory=list)
    group_ids: List[str] = Field(default_factory=list)

    # Both join tables are keyed on their two ids, so a repeated entry would
    # fail on insert as a primary key violation rather than as bad input.
    @field_validator('role_id')
    @classmethod
    def validate_role_ids(cls, v):
        if v is not None and len(set(v)) != len(v):
            raise ValueError('Role IDs must be unique')
        return v

    @field_validator('group_ids')
    @classmethod
    def validate_group_ids(cls, v):
        if v is not None and len(set(v)) != len(v):
            raise ValueError('Group IDs must be unique')
        return v

    @field_validator('email')
    @classmethod
    def validate_email_format(cls, v):
        # Check for common email patterns
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError('Invalid email format')

        # Check for consecutive dots
        if '..' in v:
            raise ValueError('Email cannot contain consecutive dots')

        # Check for valid domain
        domain = v.split('@')[1]
        if len(domain.split('.')) < 2:
            raise ValueError('Invalid email domain')

        # Check for maximum domain length (255 characters)
        if len(domain) > 255:
            raise ValueError('Email domain too long')

        # Check for valid TLD length (2-63 characters)
        tld = domain.split('.')[-1]
        if not 2 <= len(tld) <= 63:
            raise ValueError('Invalid TLD length')

        return v.lower()  # Normalize email to lowercase

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
        if not re.match(PASSWORD_REGEX, v):
            raise ValueError(
                'Password must contain at least one letter, one number, and one special character'
            )
        return v

    @field_validator('first_name')
    @classmethod
    def validate_name_format(cls, v):
        if v is not None:
            if not v.replace(' ', '').isalpha():
                raise ValueError('Name should only contain letters and spaces')
        return v

    @model_validator(mode='after')
    def validate_passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError('Password and confirm password do not match')
        return self


class UpdateUser(BaseModel):
    user_id: str = Field(..., min_length=1)
    add_role_ids: Optional[List[str]] = Field(None)
    delete_role_ids: Optional[List[str]] = Field(None)
    add_group_ids: Optional[List[str]] = Field(None)
    delete_group_ids: Optional[List[str]] = Field(None)
    email: Optional[EmailStr] = Field(None, max_length=254)
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    password: Optional[str] = Field(None, min_length=8)
    confirm_password: Optional[str] = Field(None, min_length=8)
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, max_length=50)

    @field_validator('add_role_ids', 'delete_role_ids')
    @classmethod
    def validate_role_ids(cls, v):
        if v is not None and len(set(v)) != len(v):
            raise ValueError('Role IDs must be unique')
        return v

    @field_validator('add_group_ids', 'delete_group_ids')
    @classmethod
    def validate_group_ids(cls, v):
        if v is not None and len(set(v)) != len(v):
            raise ValueError('Group IDs must be unique')
        return v

    @field_validator('email')
    @classmethod
    def validate_email_format(cls, v):
        if v is None:
            return v
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
        if not re.match(PASSWORD_REGEX, v):
            raise ValueError(
                'Password must contain at least one letter, one number, and one special character'
            )
        return v

    @field_validator('first_name')
    @classmethod
    def validate_name_format(cls, v):
        if v is not None:
            if not v.replace(' ', '').isalpha():
                raise ValueError('Name should only contain letters and spaces')
        return v

    @model_validator(mode='after')
    def validate_passwords_match(self):
        if self.password is not None or self.confirm_password is not None:
            if self.password != self.confirm_password:
                raise ValueError('Password and confirm password do not match')
        return self


class ResetUser(BaseModel):
    secret_token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)
    recaptcha_token: Optional[str] = None

    @field_validator('new_password')
    @classmethod
    def validate_password_strength(cls, v):
        if not re.match(PASSWORD_REGEX, v):
            raise ValueError(
                'Password must contain at least one letter, one number, and one special character'
            )
        return v

    @model_validator(mode='after')
    def validate_passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError('Password and confirm password do not match')
        return self
