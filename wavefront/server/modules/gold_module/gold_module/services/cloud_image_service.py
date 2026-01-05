from abc import ABC
from abc import abstractmethod
import json
from typing import Any, Dict, Tuple

import boto3
from common_module.log.logger import logger
from google.cloud import pubsub_v1
from google.cloud import storage


class CloudImageService(ABC):
    @abstractmethod
    async def upload_image(self, image_data: bytes, object_key: str) -> Tuple[str, str]:
        pass

    @abstractmethod
    async def send_message(self, message: Dict[str, Any]) -> str:
        pass

    @abstractmethod
    async def upload_image_metadata(
        self, image_metadata: bytes, object_key: str
    ) -> Tuple[str, str]:
        """Upload image metadata to the cloud storage"""
        pass


class AWSImageService(CloudImageService):
    def __init__(self, bucket_name: str, queue_url: str, region: str = 'us-east-1'):
        self.bucket_name = bucket_name
        self.queue_url = queue_url
        self.region = region

        if not self.bucket_name:
            raise ValueError('S3 bucket name must be provided for AWS')
        if not self.queue_url:
            raise ValueError('SQS queue URL must be provided for AWS')

        self.s3_client = boto3.client('s3', region_name=region)
        self.sqs_client = boto3.client('sqs', region_name=region)

    async def upload_image(self, image_data: bytes, object_key: str) -> Tuple[str, str]:
        """Upload to AWS S3"""
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=object_key,
            Body=image_data,
            ContentType='image/jpeg',
        )

        return (self.bucket_name, object_key)

    async def send_message(self, message: Dict[str, Any]) -> str:
        """Send to AWS SQS"""
        response = self.sqs_client.send_message(
            QueueUrl=self.queue_url, MessageBody=json.dumps(message)
        )

        message_id = response['MessageId']
        logger.info(f'Successfully sent message to SQS: {message_id}')
        return message_id

    async def upload_image_metadata(
        self, image_metadata: bytes, object_key: str
    ) -> Tuple[str, str]:
        """Upload image metadata to AWS S3"""
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=object_key,
            Body=image_metadata,
            ContentType='application/json',
        )

        return (self.bucket_name, object_key)


class GCPImageService(CloudImageService):
    def __init__(self, bucket_name: str, project_id: str, topic_id: str):
        """
        Args:
            bucket_name: Name of the GCS bucket
            project_id: GCP project ID
            topic_id: Pub/Sub topic ID
        """
        self.bucket_name = bucket_name
        self.project_id = project_id
        self.topic_id = topic_id

        if not self.bucket_name:
            raise ValueError('GCS bucket name must be provided for GCP')
        if not self.project_id:
            raise ValueError('Project ID must be provided for GCP')
        if not self.topic_id:
            raise ValueError('Topic ID must be provided for GCP')

        self.storage_client = storage.Client()
        self.publisher = pubsub_v1.PublisherClient()
        self.topic_path = self.publisher.topic_path(self.project_id, self.topic_id)

    async def upload_image(self, image_data: bytes, object_key: str) -> Tuple[str, str]:
        """Upload to Google Cloud Storage"""
        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(object_key)
        blob.upload_from_string(image_data, content_type='image/jpeg')

        return (self.bucket_name, object_key)

    async def upload_image_metadata(
        self, image_metadata: str, object_key: str
    ) -> Tuple[str, str]:
        """Upload image data to GCS"""
        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(object_key)
        blob.upload_from_string(image_metadata)

        return (self.bucket_name, object_key)

    async def send_message(self, message: Dict[str, Any]) -> str:
        """Send to GCP Pub/Sub"""
        data = json.dumps(message).encode('utf-8')
        future = self.publisher.publish(self.topic_path, data)
        message_id = future.result()

        logger.info(f'Successfully sent message to Pub/Sub: {message_id}')
        return message_id
