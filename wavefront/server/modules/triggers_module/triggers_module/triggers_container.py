from dependency_injector import containers, providers
from flo_cloud.kms import FloKmsService

from triggers_module.providers.gmail.gmail_oauth import GmailOAuthClient
from triggers_module.providers.gmail.gmail_provider import GmailProvider
from triggers_module.providers.gmail.pubsub_signature import PubSubPushVerifier
from triggers_module.providers.registry import TriggerProviderRegistry
from triggers_module.services.trigger_crud_service import TriggerCrudService
from triggers_module.services.trigger_event_processor import TriggerEventProcessor
from triggers_module.services.trigger_push_receiver import TriggerPushReceiver
from triggers_module.services.trigger_subscription_renewer import (
    TriggerSubscriptionRenewer,
)
from triggers_module.utils.token_crypto import TokenCrypto


def _build_registry(gmail_provider: GmailProvider) -> TriggerProviderRegistry:
    registry = TriggerProviderRegistry()
    registry.register(gmail_provider)
    return registry


class TriggersContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])

    trigger_repository = providers.Dependency()
    credential_repository = providers.Dependency()
    event_repository = providers.Dependency()
    agent_repository = providers.Dependency()
    workflow_repository = providers.Dependency()

    async_agentic_execution_service = providers.Dependency()
    cache_manager = providers.Dependency()

    kms_service = providers.Singleton(
        FloKmsService,
        cloud_provider=config.cloud_config.cloud_provider,
    )

    token_crypto = providers.Singleton(TokenCrypto, kms_service=kms_service)

    gmail_oauth_client = providers.Singleton(
        GmailOAuthClient,
        client_id=config.triggers_gmail.client_id,
        client_secret=config.triggers_gmail.client_secret,
        redirect_uri=config.triggers_gmail.redirect_uri,
    )

    gmail_pubsub_verifier = providers.Singleton(PubSubPushVerifier)

    gmail_provider = providers.Singleton(
        GmailProvider,
        oauth_client=gmail_oauth_client,
        pubsub_project_id=config.triggers_gmail.pubsub_project_id,
        pubsub_topic_prefix=config.triggers_gmail.pubsub_topic_prefix,
        push_endpoint_template=config.triggers_gmail.push_endpoint_template,
        oidc_service_account_email=config.triggers_gmail.oidc_service_account_email,
    )

    trigger_provider_registry = providers.Singleton(
        _build_registry, gmail_provider=gmail_provider
    )

    trigger_crud_service = providers.Singleton(
        TriggerCrudService,
        trigger_repository=trigger_repository,
        credential_repository=credential_repository,
        agent_repository=agent_repository,
        workflow_repository=workflow_repository,
        provider_registry=trigger_provider_registry,
        token_crypto=token_crypto,
    )

    trigger_push_receiver = providers.Singleton(
        TriggerPushReceiver,
        trigger_repository=trigger_repository,
        pubsub_verifier=gmail_pubsub_verifier,
        provider_registry=trigger_provider_registry,
    )

    trigger_event_processor = providers.Singleton(
        TriggerEventProcessor,
        trigger_repository=trigger_repository,
        credential_repository=credential_repository,
        event_repository=event_repository,
        workflow_repository=workflow_repository,
        provider_registry=trigger_provider_registry,
        token_crypto=token_crypto,
        async_execution_service=async_agentic_execution_service,
    )

    trigger_subscription_renewer = providers.Singleton(
        TriggerSubscriptionRenewer,
        trigger_repository=trigger_repository,
        credential_repository=credential_repository,
        provider_registry=trigger_provider_registry,
        token_crypto=token_crypto,
        cache_manager=cache_manager,
    )
