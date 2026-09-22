"""Unit tests for NewUser / UpdateUser / ResetUser / AuthRequest schema validation.

These cover the CWE-20 input rules (password strength, confirm match, email,
names, UUID gates) without spinning up the API stack.
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from user_management_module.controllers.auth_controller import AuthRequest
from user_management_module.models.user_schema import NewUser
from user_management_module.models.user_schema import ResetUser
from user_management_module.models.user_schema import UpdateUser

VALID_PASSWORD = 'Test@123'
USER_ID = str(uuid4())
GROUP_ID = str(uuid4())


def _new_user(**overrides) -> NewUser:
    payload = {
        'email': 'user@example.com',
        'password': VALID_PASSWORD,
        'confirm_password': VALID_PASSWORD,
        'first_name': 'Test',
        'last_name': 'User',
        'role_id': ['role_a'],
    }
    payload.update(overrides)
    return NewUser(**payload)


def _update_user(**overrides) -> UpdateUser:
    payload = {'user_id': USER_ID}
    payload.update(overrides)
    return UpdateUser(**payload)


def _reset_user(**overrides) -> ResetUser:
    payload = {
        'secret_token': 'a' * 40,
        'new_password': VALID_PASSWORD,
        'confirm_password': VALID_PASSWORD,
    }
    payload.update(overrides)
    return ResetUser(**payload)


# --- NewUser: password strength -------------------------------------------------


@pytest.mark.parametrize(
    'password',
    [
        'Test@123',
        'Abcd1234!',
        'Zyxw9876#',
        'Aa1@' + 'x' * 68,  # exactly 72 chars
    ],
)
def test_new_user_accepts_valid_passwords(password):
    user = _new_user(password=password, confirm_password=password)
    assert user.password == password


@pytest.mark.parametrize(
    'password',
    [
        'test@123',  # no uppercase
        'TEST@123',  # no lowercase
        'Test1234',  # no special
        'Test@abc',  # no digit
        'Te@1',  # too short
        'Test@123^',  # disallowed special
        'Test 123!',  # space not allowed
        'Aa1@' + 'x' * 69,  # 73 chars — over max
    ],
)
def test_new_user_rejects_weak_passwords(password):
    with pytest.raises(ValidationError) as exc:
        _new_user(password=password, confirm_password=password)
    assert (
        'password' in str(exc.value).lower() or 'value error' in str(exc.value).lower()
    )


def test_new_user_rejects_mismatched_confirm_password():
    with pytest.raises(ValidationError) as exc:
        _new_user(password=VALID_PASSWORD, confirm_password='Different@123')
    assert 'do not match' in str(exc.value).lower()


def test_new_user_requires_confirm_password():
    with pytest.raises(ValidationError):
        NewUser(
            email='user@example.com',
            password=VALID_PASSWORD,
            first_name='Test',
            role_id=['role_a'],
        )


# --- NewUser: email / names / ids ----------------------------------------------


@pytest.mark.parametrize(
    'email',
    [
        'bad',
        'bad@',
        'bad@domain',
        'a..b@example.com',
        'a@b..com',
    ],
)
def test_new_user_rejects_invalid_email(email):
    with pytest.raises(ValidationError):
        _new_user(email=email)


def test_new_user_normalizes_email_to_lowercase():
    user = _new_user(email='User@Example.COM')
    assert user.email == 'user@example.com'


@pytest.mark.parametrize('name', ['John123', 'Jane!', 'A_B', ''])
def test_new_user_rejects_invalid_names(name):
    with pytest.raises(ValidationError):
        _new_user(first_name=name)


def test_new_user_accepts_names_with_spaces():
    user = _new_user(first_name='Mary Jane', last_name='Van Gogh')
    assert user.first_name == 'Mary Jane'
    assert user.last_name == 'Van Gogh'


def test_new_user_rejects_duplicate_role_ids():
    with pytest.raises(ValidationError) as exc:
        _new_user(role_id=['role_a', 'role_a'])
    assert 'unique' in str(exc.value).lower()


def test_new_user_rejects_non_uuid_group_ids():
    with pytest.raises(ValidationError) as exc:
        _new_user(group_ids=['not-a-uuid'])
    assert 'group' in str(exc.value).lower() or 'invalid' in str(exc.value).lower()


def test_new_user_accepts_uuid_group_ids():
    user = _new_user(group_ids=[GROUP_ID])
    assert user.group_ids == [GROUP_ID]


def test_new_user_rejects_oversized_id_list():
    with pytest.raises(ValidationError):
        _new_user(role_id=[f'role_{i}' for i in range(101)])


# --- UpdateUser ----------------------------------------------------------------


def test_update_user_allows_omitting_password():
    user = _update_user(first_name='Updated')
    assert user.password is None
    assert user.confirm_password is None


def test_update_user_password_requires_matching_confirm():
    user = _update_user(password=VALID_PASSWORD, confirm_password=VALID_PASSWORD)
    assert user.password == VALID_PASSWORD


def test_update_user_rejects_mismatched_password_confirm():
    with pytest.raises(ValidationError) as exc:
        _update_user(password=VALID_PASSWORD, confirm_password='Other@123')
    assert 'do not match' in str(exc.value).lower()


def test_update_user_rejects_password_without_confirm():
    with pytest.raises(ValidationError) as exc:
        _update_user(password=VALID_PASSWORD)
    assert 'do not match' in str(exc.value).lower()


def test_update_user_rejects_confirm_without_password():
    with pytest.raises(ValidationError) as exc:
        _update_user(confirm_password=VALID_PASSWORD)
    assert 'do not match' in str(exc.value).lower()


def test_update_user_rejects_invalid_user_id():
    with pytest.raises(ValidationError) as exc:
        _update_user(user_id='not-a-uuid')
    assert 'user_id' in str(exc.value).lower() or 'invalid' in str(exc.value).lower()


def test_update_user_rejects_weak_password():
    with pytest.raises(ValidationError):
        _update_user(password='test@123', confirm_password='test@123')


# --- ResetUser -----------------------------------------------------------------


def test_reset_user_accepts_valid_payload():
    reset = _reset_user()
    assert reset.new_password == VALID_PASSWORD


def test_reset_user_rejects_mismatched_confirm():
    with pytest.raises(ValidationError) as exc:
        _reset_user(confirm_password='Other@123')
    assert 'do not match' in str(exc.value).lower()


@pytest.mark.parametrize(
    'password',
    ['test@123', 'TEST@123', 'Test1234', 'Te@1', 'Aa1@' + 'x' * 69],
)
def test_reset_user_rejects_weak_passwords(password):
    with pytest.raises(ValidationError):
        _reset_user(new_password=password, confirm_password=password)


def test_reset_user_rejects_empty_secret_token():
    with pytest.raises(ValidationError):
        _reset_user(secret_token='')


def test_reset_user_rejects_oversized_secret_token():
    with pytest.raises(ValidationError):
        _reset_user(secret_token='t' * 4097)


# --- AuthRequest (login) -------------------------------------------------------


def test_auth_request_accepts_simple_password():
    """Login must not enforce create/reset complexity — only length/email."""
    auth = AuthRequest(email='user@example.com', password='simple')
    assert auth.password == 'simple'


def test_auth_request_rejects_invalid_email():
    with pytest.raises(ValidationError):
        AuthRequest(email='not-an-email', password='simple')


def test_auth_request_rejects_empty_password():
    with pytest.raises(ValidationError):
        AuthRequest(email='user@example.com', password='')


def test_auth_request_rejects_oversized_password():
    with pytest.raises(ValidationError):
        AuthRequest(email='user@example.com', password='x' * 73)
