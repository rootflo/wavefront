import io
import os
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import IO, ContextManager, List, Optional, Tuple
from urllib.parse import quote

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    generate_blob_sas,
)

from .._types import CloudStorageHandler
from ..exceptions import CloudStorageFileNotFoundError


class AzureBlobStorage(CloudStorageHandler):
    """Azure Blob Storage implementation"""

    def __init__(
        self,
        account_url: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ):
        """
        Initialize Azure Blob Storage client.

        Two authentication modes are supported:

        1. Service Principal (explicit credentials) — closest equivalent to a
           GCP service account. Provide client_id, client_secret, and tenant_id.
           These map to an Azure App Registration with the
           "Storage Blob Data Contributor" role assigned on the storage account.

        2. DefaultAzureCredential (no credential args) — tries a chain of
           authentication methods in order: environment variables
           (AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / AZURE_TENANT_ID), Workload
           Identity, Managed Identity, Azure CLI login, etc.

        Args:
            account_url: Azure storage account URL, e.g.
                         "https://<account>.blob.core.windows.net".
                         Falls back to the AZURE_STORAGE_ACCOUNT_URL env var.
            client_id: Azure AD application (client) ID.
            client_secret: Azure AD application client secret.
            tenant_id: Azure AD tenant (directory) ID.
        """
        resolved_url = account_url or os.environ.get('AZURE_STORAGE_ACCOUNT_URL')
        if not resolved_url:
            raise ValueError(
                'account_url must be provided or AZURE_STORAGE_ACCOUNT_URL must be set'
            )
        self._account_url = resolved_url
        self._account_name = self._parse_account_name(resolved_url)

        creds_provided = [client_id, client_secret, tenant_id]
        if all(creds_provided):
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
            )
        elif any(creds_provided):
            raise ValueError(
                'Partial credentials provided. Supply all of client_id, '
                'client_secret, and tenant_id, or none to use DefaultAzureCredential.'
            )
        else:
            credential = DefaultAzureCredential()

        self._credential = credential
        self.client = BlobServiceClient(account_url=resolved_url, credential=credential)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_account_name(account_url: str) -> str:
        """Extract the storage account name from the account URL."""
        match = re.match(r'https://([^.]+)\.blob\.core\.windows\.net', account_url)
        if not match:
            raise ValueError(
                f'Cannot parse account name from account_url: {account_url!r}'
            )
        return match.group(1)

    # ------------------------------------------------------------------
    # CloudStorageHandler interface
    # ------------------------------------------------------------------

    def get_file(self, bucket_name: str, file_path: str) -> bytes:
        """
        Download a blob from an Azure container.

        Args:
            bucket_name: Name of the Azure container (equivalent to S3 bucket).
            file_path: Path / name of the blob inside the container.

        Returns:
            File content as bytes.

        Raises:
            CloudStorageFileNotFoundError: If the blob or container does not exist.
            Exception: For other errors.
        """
        try:
            blob_client = self.client.get_blob_client(
                container=bucket_name, blob=file_path
            )
            return blob_client.download_blob().readall()
        except ResourceNotFoundError:
            raise CloudStorageFileNotFoundError(bucket_name, file_path)
        except Exception as e:
            raise Exception(f'Error reading file from Azure Blob Storage: {str(e)}')

    def save_large_file(
        self,
        data: bytes,
        bucket_name: str,
        key: str,
        content_type: Optional[str] = None,
    ) -> None:
        """
        Upload a large file to Azure Blob Storage using chunked upload.

        Azure's SDK handles chunked (block blob) upload automatically via
        upload_blob when a BytesIO stream is provided.

        Args:
            data: File data in bytes.
            bucket_name: Name of the Azure container.
            key: Blob name / path inside the container.
            content_type: MIME type of the file (optional).
        """
        try:
            blob_client = self.client.get_blob_client(container=bucket_name, blob=key)
            kwargs = {'overwrite': True}
            if content_type is not None:
                kwargs['content_settings'] = _content_settings(content_type)

            blob_client.upload_blob(io.BytesIO(data), **kwargs)
        except Exception as e:
            raise Exception(
                f'Error uploading large file to Azure Blob Storage: {str(e)}'
            )

    def save_small_file(
        self,
        file_content: bytes,
        bucket_name: str,
        key: str,
        content_type: Optional[str] = None,
    ) -> None:
        """
        Upload a small file to Azure Blob Storage in a single operation.

        Args:
            file_content: File content in bytes.
            bucket_name: Name of the Azure container.
            key: Blob name / path inside the container.
            content_type: MIME type of the file (optional).
        """
        try:
            blob_client = self.client.get_blob_client(container=bucket_name, blob=key)
            kwargs = {'overwrite': True}
            if content_type is not None:
                kwargs['content_settings'] = _content_settings(content_type)

            blob_client.upload_blob(file_content, **kwargs)
        except Exception as e:
            raise Exception(
                f'Error uploading small file to Azure Blob Storage: {str(e)}'
            )

    def delete_file(self, bucket_name: str, file_path: str) -> None:
        """
        Delete a blob from an Azure container.

        Args:
            bucket_name: Name of the Azure container.
            file_path: Blob name / path inside the container.
        """
        try:
            blob_client = self.client.get_blob_client(
                container=bucket_name, blob=file_path
            )
            blob_client.delete_blob()
        except ResourceNotFoundError:
            raise CloudStorageFileNotFoundError(bucket_name, file_path)
        except Exception as e:
            raise Exception(f'Error deleting file from Azure Blob Storage: {str(e)}')

    def get_bucket_key(self, value: str) -> Tuple[str, str]:
        """
        Parse an azure:// URL into (container_name, blob_key).

        Args:
            value: URL in the format "azure://container-name/blob-path".

        Returns:
            Tuple of (container_name, blob_key).
        """
        match = re.match(r'azure://([^/]+)/(.+)', value)
        if not match:
            raise ValueError(
                f'Invalid Azure Blob Storage URL format: {value!r}. '
                'Expected azure://container-name/blob-path'
            )
        return match.group(1), match.group(2)

    def generate_presigned_url(
        self, bucket_name: str, key: str, type: str, expiresIn: int = 300
    ) -> str:
        """
        Generate a SAS (Shared Access Signature) URL for a blob.

        Azure's equivalent of S3 presigned URLs / GCS signed URLs are SAS tokens.
        The returned URL is the full blob URL with the SAS token appended.

        Args:
            bucket_name: Name of the Azure container.
            key: Blob name / path inside the container.
            type: HTTP method — 'GET', 'PUT', or 'POST' (case-insensitive).
            expiresIn: Expiration time in seconds (default: 300).

        Returns:
            Full SAS URL as a string.

        Raises:
            ValueError: If type is not supported.
            Exception: If SAS generation fails.
        """
        try:
            method = type.upper()
            permissions = _sas_permissions(method)

            expiry = datetime.now(timezone.utc) + timedelta(seconds=expiresIn)

            # generate_blob_sas requires a user_delegation_key or account_key.
            # We obtain a user delegation key using our credential, which works
            # with both service principal and DefaultAzureCredential.
            start = datetime.now(timezone.utc) - timedelta(seconds=60)
            udk = self.client.get_user_delegation_key(
                key_start_time=start, key_expiry_time=expiry
            )

            sas_token = generate_blob_sas(
                account_name=self._account_name,
                container_name=bucket_name,
                blob_name=key,
                user_delegation_key=udk,
                permission=permissions,
                expiry=expiry,
            )

            encoded_key = quote(key, safe='/')
            blob_url = f'{self._account_url}/{bucket_name}/{encoded_key}?{sas_token}'
            return blob_url
        except Exception as e:
            raise Exception(
                f'Error generating SAS URL for Azure Blob Storage: {str(e)}'
            )

    def list_files(
        self, bucket_name: str, prefix: str, page_size: int = 50, page_number: int = 1
    ) -> Tuple[List[str], bool]:
        """
        List blobs in an Azure container with prefix filtering and pagination.

        Args:
            bucket_name: Name of the Azure container.
            prefix: Prefix to filter blobs by name.
            page_size: Number of blobs per page (default: 50).
            page_number: 1-based page number (default: 1).

        Returns:
            Tuple of (list of blob names, has_next_page).

        Raises:
            Exception: If listing fails.
        """
        try:
            if page_number < 1:
                raise ValueError('page_number must be >= 1')
            if page_size < 1:
                raise ValueError('page_size must be >= 1')

            container_client = self.client.get_container_client(bucket_name)
            pages = container_client.list_blobs(
                name_starts_with=prefix, results_per_page=page_size
            ).by_page()

            # Advance to the requested page (1-based)
            try:
                for _ in range(page_number):
                    current_page = next(pages)
            except StopIteration:
                return [], False

            blob_names = [blob.name for blob in current_page]

            try:
                next(pages)
                has_next_page = True
            except StopIteration:
                has_next_page = False

            return blob_names, has_next_page

        except ResourceNotFoundError:
            raise Exception(f'Container {bucket_name} not found')
        except Exception as e:
            raise Exception(f'Error listing files from Azure Blob Storage: {str(e)}')

    def open_text_writer(
        self, bucket_name: str, key: str, content_type: Optional[str] = None
    ) -> ContextManager[IO[str]]:
        """
        Open a text-mode writer for Azure Blob Storage.

        Azure SDK does not provide a native streaming text writer, so this
        follows the same pattern as the S3 implementation: buffer content in
        memory via StringIO and upload on context exit.
        """

        @contextmanager
        def _writer() -> IO[str]:
            buffer = io.StringIO()
            try:
                yield buffer
                data = buffer.getvalue().encode('utf-8')
                self.save_large_file(data, bucket_name, key, content_type)
            finally:
                buffer.close()

        return _writer()


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------


def _content_settings(content_type: str):
    """Build a ContentSettings object for the given MIME type."""
    from azure.storage.blob import ContentSettings

    return ContentSettings(content_type=content_type)


def _sas_permissions(method: str) -> BlobSasPermissions:
    """Map an HTTP method string to the corresponding BlobSasPermissions."""
    if method == 'GET':
        return BlobSasPermissions(read=True)
    elif method == 'PUT':
        return BlobSasPermissions(write=True, create=True)
    elif method == 'POST':
        return BlobSasPermissions(write=True, create=True)
    raise ValueError(
        f"Unsupported SAS permission type: {method!r}. Expected 'GET', 'PUT', or 'POST'."
    )
