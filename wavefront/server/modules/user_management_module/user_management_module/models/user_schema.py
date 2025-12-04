import re
from typing import List, Optional

from pydantic import BaseModel
from pydantic import EmailStr
from pydantic import Field
from pydantic import field_validator

PASSWORD_REGEX = r'^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$'


class NewUser(BaseModel):
    email: EmailStr = Field(..., max_length=254)  # RFC 5321 standard max length
    password: str = Field(..., min_length=8)
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, max_length=50)
    team_id: Optional[str] = None
    role_id: List[str] = Field(..., min_length=1)

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


class UpdateUser(BaseModel):
    user_id: str = Field(..., min_length=1)
    add_role_ids: Optional[List[str]] = Field(None)
    delete_role_ids: Optional[List[str]] = Field(None)

    @field_validator('add_role_ids', 'delete_role_ids')
    @classmethod
    def validate_role_ids(cls, v):
        if v is not None and len(set(v)) != len(v):
            raise ValueError('Role IDs must be unique')
        return v


class ResetUser(BaseModel):
    secret_token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)

    @field_validator('new_password')
    @classmethod
    def validate_password_strength(cls, v):
        if not re.match(PASSWORD_REGEX, v):
            raise ValueError(
                'Password must contain at least one letter, one number, and one special character'
            )
        return v
