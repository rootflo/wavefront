PASSWORD_RESET_SUBJECT = 'Reset Your Password'


def build_password_reset_email(reset_url: str) -> str:
    """HTML body for the password reset mail.

    The 10 minute validity stated here is the reset token's expiry; keep the two
    in step if that changes.
    """
    return f"""
            <p>Hello,</p>
            <p>We received a request to reset your password. Click the link below to set a new password:</p>
            <p><a href="{reset_url}" target="_blank" style="color: #007bff; text-decoration: none;">Reset Your Password</a></p>
            <p><strong>Note:</strong> This link is valid for <strong>10 minutes</strong>. If you do not reset your password within this time, you will need to request a new link.</p>
            <p>If you did not request this, please contact the administrator immediately.</p>
            """
