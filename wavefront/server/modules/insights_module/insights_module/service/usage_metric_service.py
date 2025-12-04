from insights_module.repository.pvo_repository import PVORepository


class UsageMetricService:
    def __init__(self, repository: PVORepository, cloud_provider: str):
        self.repository = repository
        self.cloud_provider = cloud_provider

    def fetch_usage_metrics(self, start_time: str, end_time: str):
        return self.repository.fetch_usage_metrics(
            start_time=start_time, end_time=end_time, cloud_provider=self.cloud_provider
        )
