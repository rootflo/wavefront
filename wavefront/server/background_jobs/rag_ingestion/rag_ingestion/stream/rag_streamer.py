from flo_utils.streaming.stream_listner import StreamListener
from flo_cloud._types import MessageQueueDict
from flo_utils.streaming.event_message import BaseEventMessage
from typing import List

from rag_ingestion.models.rag_message import RagEventMessage


class RagStreamListener(StreamListener):
    def get_event_messages(
        self, messages: List[MessageQueueDict]
    ) -> List[BaseEventMessage]:
        return [self.__make_event_message(msg) for msg in messages]

    def __make_event_message(self, message: MessageQueueDict) -> RagEventMessage:
        bucket_name, bucket_key, kb_id, doc_id, parse_type, file_type = (
            self.__fetch_bucket_details(message.body)
        )
        return RagEventMessage(
            id=message.id,
            ack_id=message.ack_id,
            bucket_name=bucket_name,
            bucket_key=bucket_key,
            kb_id=kb_id,
            doc_id=doc_id,
            parse_type=parse_type,
            file_type=file_type,
            body=message.body,
        )

    def __fetch_bucket_details(self, body: dict):
        bucket_name = body['bucket'] if 'bucket' in body else body['bucket_name']
        bucket_key = body['name'] if 'name' in body else body['key']
        kb_id = body['kb_id'] if 'kb_id' in body else None
        doc_id = body['doc_id'] if 'doc_id' in body else None
        parse_type = body['parse_type'] if 'parse_type' in body else None
        file_type = body['file_type'] if 'file_type' in body else None
        return bucket_name, bucket_key, kb_id, doc_id, parse_type, file_type
