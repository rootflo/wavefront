from abc import ABC, abstractmethod
from typing import Any
from common_module.log.logger import logger
from fastapi import HTTPException
from fastapi import status
import msal
import requests
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


class EmailService(ABC):
    @abstractmethod
    def get_access_token(self):
        pass

    @abstractmethod
    def send_forget_password_email(self, forget_url_link: str, email: str) -> bool:
        pass

    @abstractmethod
    def send_email(
        self,
        subject: str,
        body: str,
        email_id: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> bool:
        pass


class OutlookEmailService(EmailService):
    def __init__(self, client_id, client_secret, tenant_id, email_sender):
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.email_sender = email_sender

    def get_access_token(self):
        authority = f'https://login.microsoftonline.com/{self.tenant_id}'
        app = msal.ConfidentialClientApplication(
            self.client_id, self.client_secret, authority
        )
        token = app.acquire_token_for_client(
            scopes=['https://graph.microsoft.com/.default']
        )
        return token['access_token']

    def send_forget_password_email(self, forget_url_link: str, email: str) -> bool:
        access_token = self.get_access_token()
        if not access_token:
            logger.error('failed to obtain outlook access token')
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Failed to authenticate while sending the email.',
            )

        url = f'https://graph.microsoft.com/v1.0/users/{self.email_sender}/sendMail'

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }

        email_data = {
            'message': {
                'subject': 'Reset Your Password',
                'body': {
                    'contentType': 'HTML',
                    'content': f"""
                <p>Hello,</p>
                <p>We received a request to reset your password. Click the link below to set a new password:</p>
                <p><a href="{forget_url_link}" target="_blank" style="color: #007bff; text-decoration: none;">Reset Your Password</a></p>
                <p><strong>Note:</strong> This link is valid for <strong>10 minutes</strong>. If you do not reset your password within this time, you will need to request a new link.</p>
                <p>If you did not request this, please contact the administrator immediately.</p>
            """,
                },
                'toRecipients': [{'emailAddress': {'address': email}}],
            }
        }

        response = requests.post(url, headers=headers, json=email_data, timeout=10)
        return response.status_code == 202

    def send_email(
        self,
        subject: str,
        body: str,
        email_id: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> bool:
        access_token = self.get_access_token()
        if not access_token:
            logger.error('failed to obtain outlook access token')
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Failed to authenticate while sending the email.',
            )
        url = f'https://graph.microsoft.com/v1.0/users/{self.email_sender}/sendMail'
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }
        message_data = {
            'message': {
                'subject': subject,
                'body': {'contentType': 'HTML', 'content': body},
                'toRecipients': [{'emailAddress': {'address': email_id}}],
            }
        }
        if attachments:
            message_data['message']['attachments'] = [
                {
                    '@odata.type': '#microsoft.graph.fileAttachment',
                    'name': attachment['filename'],
                    'contentType': attachment.get(
                        'mime_type', 'application/octet-stream'
                    ),
                    'contentBytes': base64.b64encode(
                        attachment['content_bytes']
                    ).decode('utf-8'),
                }
                for attachment in attachments
            ]
        response = requests.post(url, headers=headers, json=message_data, timeout=10)
        return response.status_code == 202


class GmailEmailService(EmailService):
    def __init__(self, client_id, client_secret, refresh_token, email_sender):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.email_sender = email_sender
        self.scopes = ['https://www.googleapis.com/auth/gmail.send']

        if not all([client_id, client_secret, refresh_token, email_sender]):
            logger.warning(
                'Gmail OAuth credentials are incomplete '
                '(client_id, client_secret, refresh_token, email_sender). '
                'Email sending will fail if attempted.'
            )

    def _assert_credentials(self):
        if not all(
            [self.client_id, self.client_secret, self.refresh_token, self.email_sender]
        ):
            raise ValueError(
                'Gmail OAuth requires client_id, client_secret, refresh_token, and email_sender'
            )

    def get_credentials(self) -> Credentials:
        self._assert_credentials()
        creds = Credentials(
            token=None,
            refresh_token=self.refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=self.scopes,
        )
        creds.refresh(Request())
        return creds

    def get_access_token(self):
        return self.get_credentials()

    def _get_gmail_service(self):
        return build('gmail', 'v1', credentials=self.get_credentials())

    def send_forget_password_email(self, forget_url_link: str, email: str) -> bool:
        try:
            service = self._get_gmail_service()

            message = MIMEMultipart()
            message['to'] = email
            message['from'] = self.email_sender
            message['subject'] = 'Reset Your Password'

            html_content = f"""
            <p>Hello,</p>
            <p>We received a request to reset your password. Click the link below to set a new password:</p>
            <p><a href="{forget_url_link}" target="_blank" style="color: #007bff; text-decoration: none;">Reset Your Password</a></p>
            <p><strong>Note:</strong> This link is valid for <strong>10 minutes</strong>. If you do not reset your password within this time, you will need to request a new link.</p>
            <p>If you did not request this, please contact the administrator immediately.</p>
            """

            html_part = MIMEText(html_content, 'html')
            message.attach(html_part)

            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            send_message = (
                service.users()
                .messages()
                .send(userId='me', body={'raw': raw_message})
                .execute()
            )

            logger.info(f"Gmail message sent successfully: {send_message['id']}")
            return True

        except ValueError:
            raise
        except Exception as e:
            logger.error(f'Error sending Gmail email: {e}')
            return False

    def send_email(
        self,
        subject: str,
        body: str,
        email_id: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> bool:
        try:
            service = self._get_gmail_service()
            message = MIMEMultipart()
            message['to'] = email_id
            message['from'] = f'Rootflo Notifications <{self.email_sender}>'
            message['subject'] = subject
            message.attach(MIMEText(body, 'html'))
            for attachment in attachments or []:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment['content_bytes'])
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{attachment["filename"]}"',
                )
                message.attach(part)
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            send_message = (
                service.users()
                .messages()
                .send(userId='me', body={'raw': raw_message})
                .execute()
            )
            logger.info(f"Gmail message sent successfully: {send_message['id']}")
            return True
        except ValueError:
            raise
        except Exception as e:
            logger.error(f'Error sending Gmail email: {e}')
            return False
