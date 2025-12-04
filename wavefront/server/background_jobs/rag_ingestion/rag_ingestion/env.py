from dotenv import load_dotenv
import os

load_dotenv()

CLOUD_PROVIDER = os.getenv('CLOUD_PROVIDER', 'gcp')
RETRY_COUNT = os.getenv('RETRY_COUNT', 3)
EMBEDDING_SERVICE_URL = os.getenv('EMBEDDING_SERVICE_URL')
FLOWARE_SERVICE_URL = os.getenv('FLOWARE_SERVICE_URL')
APP_ENV = os.getenv('APP_ENV', 'dev')
PASSTHROUGH_SECRET = os.getenv('PASSTHROUGH_SECRET')
