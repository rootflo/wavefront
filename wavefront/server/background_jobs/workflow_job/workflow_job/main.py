from dotenv import load_dotenv

# ruff: noqa: E402
load_dotenv()

from flo_cloud.message_queue import MessageQueueManager
from db_repo_module.cache.cache_manager import CacheManager
from workflow_job.workflow_listener import WorkflowListener
from workflow_job.workflow_processor import WorkflowMessageProcessor
from flo_cloud.cloud_storage import CloudStorageManager

from api_services_module.api_services_container import create_api_services_container
from db_repo_module.db_repo_container import DatabaseModuleContainer
from common_module.common_container import CommonContainer
from api_services_module.api_services_container import ApiServicesContainer
from agents_module.agents_container import AgentsContainer
from tools_module.tools_container import ToolsContainer
from plugins_module.plugins_container import PluginsContainer


db_repo_container = DatabaseModuleContainer()
common_container = CommonContainer(cache_manager=db_repo_container.cache_manager)
config = common_container.config()

# API Services Container
api_services_container: ApiServicesContainer = create_api_services_container(
    api_service_repository=db_repo_container.api_services_repository,
    cloud_storage_manager=common_container.cloud_storage_manager,
    db_client=db_repo_container.db_client,
    cache_manager=db_repo_container.cache_manager,
    response_formatter=common_container.response_formatter,
)

tools_container = ToolsContainer()

agents_container = AgentsContainer(
    db_client=db_repo_container.db_client,
    cloud_storage_manager=common_container.cloud_storage_manager,
    cache_manager=db_repo_container.cache_manager,
    tool_loader=tools_container.tool_loader,
    workflow_pipeline_repository=db_repo_container.workflow_pipeline_repository,
    workflow_runs_repository=db_repo_container.workflow_runs_repository,
    namespace_repository=db_repo_container.namespace_repository,
    agent_repository=db_repo_container.agent_repository,
    workflow_repository=db_repo_container.workflow_repository,
)

plugins_container = PluginsContainer(
    db_client=db_repo_container.db_client,
    cloud_manager=common_container.cloud_storage_manager,
    dynamic_query_repository=db_repo_container.dynamic_query_repository,
    cache_manager=db_repo_container.cache_manager,
)

common_container.wire(
    modules=[__name__],
    packages=[
        'plugins_module.controllers',
        'plugins_module.services',
        'user_management_module.controllers',
        'user_management_module.authorization',
    ],
)

plugins_container.wire(
    modules=[__name__],
    packages=[
        'plugins_module.controllers',
        'plugins_module.services',
        'user_management_module.controllers',
        'user_management_module.authorization',
        'tools_module.datasources',
    ],
)

api_services_container.wire(
    modules=[__name__],
    packages=[
        'api_services_module.execution',
    ],
)


def main():
    message_queue_manager = MessageQueueManager(
        config['cloud_config']['cloud_provider']
    )
    cloud_storage_manager = CloudStorageManager(
        config['cloud_config']['cloud_provider']
    )
    cache_manager = CacheManager(namespace='workflow-worker')

    # Initialize stream listener
    listener = WorkflowListener(
        event_manager=message_queue_manager,
        processor=WorkflowMessageProcessor(
            cloud_storage_manager=cloud_storage_manager,
            cache_manager=cache_manager,
            workflow_inference_service=agents_container.workflow_inference_service(),
            floware_service_url=config['floware']['service_url'],
            app_env=config['app_config']['app_env'],
            passthrough_secret=config['app_config']['passthrough_secret'],
        ),
        cache_manager=cache_manager,
        retry_count=3,
        streaming_batch_size=int(config['app_config']['batch_size']),
    )

    listener.run_workers(thread_count=int(config['app_config']['thread_count']))


if __name__ == '__main__':
    main()
