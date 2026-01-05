from abc import ABC, abstractmethod
from common_module.log.logger import logger
from fastapi import HTTPException
from fastapi import status
import msal
import requests
import base64
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.oauth2 import service_account
from googleapiclient.discovery import build


class EmailService(ABC):
    @abstractmethod
    def get_access_token(self):
        pass

    @abstractmethod
    def send_forget_password_email(self, forget_url_link: str, email: str) -> bool:
        pass

    @abstractmethod
    def send_email(self, subject: str, body: str, email_id: str) -> bool:
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

        response = requests.post(url, headers=headers, json=email_data)
        return response.status_code == 202

    def send_email(self, subject: str, body: str, email_id: str) -> bool:
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
                'subject': subject,
                'body': body,
                'toRecipients': [{'emailAddress': {'address': email_id}}],
            }
        }
        response = requests.post(url, headers=headers, json=email_data)
        return response.status_code == 202


class GmailEmailService(EmailService):
    def __init__(self, service_account_b64, email_sender, delegate_user):
        self.email_sender = email_sender or delegate_user
        self.delegate_user = delegate_user
        self.scopes = ['https://www.googleapis.com/auth/gmail.send']

        if not delegate_user:
            raise Exception('Delegate user required for gmail')

        try:
            decoded_json = base64.b64decode(service_account_b64).decode('utf-8')
            self.service_account_info = json.loads(decoded_json)
        except Exception as e:
            raise Exception(f'Invalid Gmail service account configuration: {str(e)}')

    def get_access_token(self):
        credentials = service_account.Credentials.from_service_account_info(
            self.service_account_info, scopes=self.scopes
        )

        credentials = credentials.with_subject(self.delegate_user)

        return credentials

    def send_forget_password_email(self, forget_url_link: str, email: str) -> bool:
        try:
            credentials = self.get_access_token()
            if not credentials:
                logger.error('failed to obtain gmail access token')
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail='Failed to authenticate while sending the email.',
                )
            service = build('gmail', 'v1', credentials=credentials)

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

        except Exception as e:
            logger.error(f'Error sending Gmail email: {e}')
            return False

    def send_email(self, subject: str, body: str, email_id: str) -> bool:
        try:
            credentials = self.get_access_token()
            if not credentials:
                logger.error('failed to obtain gmail access token')
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail='Failed to authenticate while sending the email.',
                )
            service = build('gmail', 'v1', credentials=credentials)
            message = MIMEMultipart()
            message['to'] = email_id
            message['from'] = self.email_sender
            message['subject'] = subject
            message.attach(MIMEText(body, 'html'))
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            send_message = (
                service.users()
                .messages()
                .send(userId='me', body={'raw': raw_message})
                .execute()
            )
            logger.info(f"Gmail message sent successfully: {send_message['id']}")
            return True
        except Exception as e:
            logger.error(f'Error sending Gmail email: {e}')
            return False
