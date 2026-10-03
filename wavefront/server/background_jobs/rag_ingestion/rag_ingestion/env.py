from dotenv import load_dotenv
import os

load_dotenv()

CLOUD_PROVIDER = os.getenv('CLOUD_PROVIDER', 'gcp')
RETRY_COUNT = int(os.getenv('RETRY_COUNT', 3))
INFERENCE_SERVICE_URL = os.getenv('INFERENCE_SERVICE_URL')
FLOWARE_SERVICE_URL = os.getenv('FLOWARE_SERVICE_URL')
APP_ENV = os.getenv('APP_ENV', 'dev')
PASSTHROUGH_SECRET = os.getenv('PASSTHROUGH_SECRET')
STREAMING_BATCH_SIZE = int(os.getenv('STREAMING_BATCH_SIZE', 5))
# Images per call to the inference service's batch endpoint. Keep at or below
# the service's MAX_EMBEDDING_BATCH_SIZE (8 by default); a larger batch is
# rejected and falls back to one call per image.
IMAGE_EMBEDDING_BATCH_SIZE = int(os.getenv('IMAGE_EMBEDDING_BATCH_SIZE', 8))
# floware's APP_NAME: index status events go to a Redis Stream under floware's
# CacheManager namespace, so this must match it.
FLOWARE_APP_NAME = os.getenv('FLOWARE_APP_NAME', 'floware')
# Texts per call to the inference app's text embedding endpoint. Keep at or
# below its MAX_TEXT_EMBEDDING_BATCH_SIZE (16 by default) or calls get a 413.
TEXT_EMBEDDING_BATCH_SIZE = int(os.getenv('TEXT_EMBEDDING_BATCH_SIZE', 16))
