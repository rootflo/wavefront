from abc import ABC
from abc import abstractmethod
import json
import re

import boto3
from common_module.utils.odata_parser import prepare_odata_filter
from google.cloud import storage
from insights_module.service.insights_service import InsightsService
from flo_cloud.gcp.gcs import GCSStorage


class PdoService(ABC):
    @abstractmethod
    def fetch_upto_limit(
        self, filter: str | None, limit: int, offset: int, table_name: str = None
    ):
        pass

    @abstractmethod
    def patch_record_by_id(self, id: str, table_name: str = None):
        pass

    @abstractmethod
    def fetch_audio(self):
        pass

    @abstractmethod
    def fetch_transcript(self):
        pass


class AWSServices(PdoService):
    def __init__(
        self,
        insights_service: InsightsService,
        transcript_bucket_name,
        audio_bucket_name,
    ):
        self._insight_service = insights_service
        self._transcript_bucket_name = transcript_bucket_name
        self._audio_bucket_name = audio_bucket_name

    def get_bucket_key(self, value: str):
        match = re.match(r's3://([^/]+)/(.+)', value)
        bucket_name = match.group(1)
        key = match.group(2)
        return bucket_name, key

    def fetch_upto_limit(self, filter, limit, offset, table_name=None):
        odata_filter, params = prepare_odata_filter(filter)
        return self._insight_service.fetch_pvo_records(
            odata_query=odata_filter,
            params=params,
            limit=limit,
            offset=offset,
            table_name=table_name,
        )

    def fetch_audio(self, url):
        audio_bucket_name, key = self.get_bucket_key(url)

        s3_client = boto3.client('s3')
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': audio_bucket_name, 'Key': key},
            ExpiresIn=1800,
        )

        return presigned_url

    def fetch_transcript(self, url):
        transcript_bucket_name, key = self.get_bucket_key(url)
        s3_client = boto3.client('s3')
        s3_response = s3_client.get_object(
            Bucket=transcript_bucket_name,
            Key=key,
        )
        file_content = s3_response['Body'].read()
        transcript_result: dict = json.loads(file_content)

        transcripts = {
            'transcript': transcript_result['transcribe'],
            'translate': transcript_result['translate'],
            'transcribe_diarized': transcript_result.get('transcribe_diarized', None),
            'translated_diarization': transcript_result.get(
                'translated_diarization', None
            ),
            'speaker_mapping': transcript_result.get('speaker_mapping', None),
            'translation_diarization': transcript_result.get(
                'translation_diarization', False
            ),
            'diarization': transcript_result.get('diarization', False),
        }
        return transcripts

    def patch_record_by_id(self, id, table_name=None):
        raise NotImplementedError(
            'Patch operation is not implemented for AWS services.'
        )


class GCPServices(PdoService):
    def __init__(
        self,
        insights_service: InsightsService,
        transcript_bucket_name,
        audio_bucket_name,
    ):
        self._insight_service = insights_service
        self._transcript_bucket_name = transcript_bucket_name
        self._audio_bucket_name = audio_bucket_name
        self.client = storage.Client()
        self.storage = GCSStorage()

    def get_bucket_key(self, value: str):
        match = re.match(r'gs://([^/]+)/(.+)', value)
        bucket_name = match.group(1)
        key = match.group(2)
        return bucket_name, key

    def fetch_upto_limit(self, filter, limit, offset, table_name=None):
        odata_filter, params = prepare_odata_filter(filter)
        return self._insight_service.fetch_pvo_records(
            odata_query=odata_filter,
            params=params,
            limit=limit,
            offset=offset,
            table_name=table_name,
        )

    def fetch_audio(self, url):
        audio_bucket_name, key = self.get_bucket_key(url)

        presigned_url = self.storage.generate_presigned_url(
            bucket_name=audio_bucket_name,
            key=key,
            type='GET',
            expiresIn=300,
        )

        return presigned_url

    def fetch_transcript(self, url):
        transcript_bucket_name, key = self.get_bucket_key(url)

        bucket = self.client.bucket(transcript_bucket_name)
        blob = bucket.blob(key)
        file_content = blob.download_as_bytes()
        transcript_result = json.loads(file_content)

        transcripts = {
            'transcript': transcript_result['transcribe'],
            'translate': transcript_result['translate'],
        }

        return transcripts

    def patch_record_by_id(self, id, update_data: dict, table_name, rls_filter: str):
        odata_filter, params = prepare_odata_filter(rls_filter)
        return self._insight_service.update_pvo_records_by_id(
            id=id,
            table_name=table_name,
            rls_filter=odata_filter,
            rls_params=params,
            update_data=update_data,
        )
