import os

# Must be set before call_processing.server is imported (it loads config.ini at import)
os.environ.setdefault('APP_ENV', 'dev')
os.environ.setdefault('PASSTHROUGH_SECRET', 'test-passthrough-secret')
