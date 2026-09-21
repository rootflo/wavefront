from dependency_injector import containers, providers

from triggers_module.services.trigger_crud_service import TriggerCrudService
from triggers_module.services.trigger_event_processor import TriggerEventProcessor
from triggers_module.services.trigger_push_receiver import TriggerPushReceiver
from triggers_module.services.trigger_subscription_renewer import (
    TriggerSubscriptionRenewer,
)
from triggers_module.utils.gmail_watch_config import build_gmail_watch_config


class TriggersContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])

    trigger_repository = providers.Dependency()
    event_repository = providers.Dependency()
    agent_repository = providers.Dependency()
    workflow_repository = providers.Dependency()

    # Mailbox credentials and OAuth apps live in plugins_module. Pub/Sub watch
    # plumbing is platform config owned by this module.
    email_connection_service = providers.Dependency()

    async_agentic_execution_service = providers.Dependency()
    cache_manager = providers.Dependency()

    gmail_watch_config = providers.Singleton(
        build_gmail_watch_config,
        pubsub_project_id=config.triggers_gmail.pubsub_project_id,
        push_endpoint_template=config.triggers_gmail.push_endpoint_template,
        pubsub_topic_prefix=config.triggers_gmail.pubsub_topic_prefix,
        oidc_service_account_email=config.triggers_gmail.oidc_service_account_email,
    )

    trigger_crud_service = providers.Singleton(
        TriggerCrudService,
        trigger_repository=trigger_repository,
        agent_repository=agent_repository,
        workflow_repository=workflow_repository,
        email_connection_service=email_connection_service,
        gmail_watch_config=gmail_watch_config,
    )

    trigger_push_receiver = providers.Singleton(
        TriggerPushReceiver,
        trigger_repository=trigger_repository,
        email_connection_service=email_connection_service,
    )

    trigger_event_processor = providers.Singleton(
        TriggerEventProcessor,
        trigger_repository=trigger_repository,
        event_repository=event_repository,
        workflow_repository=workflow_repository,
        email_connection_service=email_connection_service,
        async_execution_service=async_agentic_execution_service,
    )

    trigger_subscription_renewer = providers.Singleton(
        TriggerSubscriptionRenewer,
        trigger_repository=trigger_repository,
        email_connection_service=email_connection_service,
        cache_manager=cache_manager,
    )
