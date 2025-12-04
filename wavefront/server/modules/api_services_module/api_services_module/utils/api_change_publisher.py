from db_repo_module.cache.cache_manager import CacheManager
import json
from dataclasses import dataclass, asdict
from typing import Optional

REDIS_API_SERVICE_UPDATES_CHANNEL = 'floware/api_service/updates'


@dataclass
class UpdateMessage:
    service_id: str
    operation: str
    metadata: Optional[dict] = None


class ApiChangePublisher:
    def __init__(self, cache_manager: CacheManager):
        self.cache_manager = cache_manager

    def publish_message(self, message: UpdateMessage):
        self.cache_manager.publish(
            channel=REDIS_API_SERVICE_UPDATES_CHANNEL,
            message=json.dumps(asdict(message)),
        )
