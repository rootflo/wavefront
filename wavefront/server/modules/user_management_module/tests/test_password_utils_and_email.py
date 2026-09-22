"""Unit tests for password hashing and password-reset email template."""

from user_management_module.utils.email_templates import (
    PASSWORD_RESET_SUBJECT,
    build_password_reset_email,
)
from user_management_module.utils.password_utils import hash_password, verify_password


def test_hash_and_verify_password_round_trip():
    hashed = hash_password('Secret@123')
    assert hashed != 'Secret@123'
    assert verify_password('Secret@123', hashed) is True
    assert verify_password('wrong', hashed) is False


def test_build_password_reset_email_includes_url_and_expiry_note():
    html = build_password_reset_email('https://app.example.com/reset?token=abc')
    assert 'https://app.example.com/reset?token=abc' in html
    assert '10 minutes' in html
    assert PASSWORD_RESET_SUBJECT == 'Reset Your Password'
