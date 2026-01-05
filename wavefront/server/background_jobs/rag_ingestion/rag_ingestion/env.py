from dotenv import load_dotenv
import os

load_dotenv()

CLOUD_PROVIDER = os.getenv('CLOUD_PROVIDER', 'gcp')
RETRY_COUNT = os.getenv('RETRY_COUNT', 3)
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
EMBEDDING_SERVICE_URL = os.getenv('EMBEDDING_SERVICE_URL')
FLOWARE_SERVICE_URL = os.getenv('FLOWARE_SERVICE_URL')
APP_ENV = os.getenv('APP_ENV', 'dev')
PASSTHROUGH_SECRET = os.getenv('PASSTHROUGH_SECRET')
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')
