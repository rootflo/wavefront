from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.database.connection import DatabaseClient
from db_repo_module.database.connection import DatabaseConfig
from db_repo_module.models.auth_secrets import AuthSecrets
from db_repo_module.models.datasource import Datasource
from db_repo_module.models.email import Email
from db_repo_module.models.kb_inferences import KnowledgeBaseInferences
from db_repo_module.models.knowledge_base_documents import KnowledgeBaseDocuments
from db_repo_module.models.knowledge_base_embeddings import KnowledgeBaseEmbeddings
from db_repo_module.models.knowledge_bases import KnowledgeBase
from db_repo_module.models.notification_users import NotificationUser
from db_repo_module.models.notifications import Notification
from db_repo_module.models.oauth_credential import OAuthCredential
from db_repo_module.models.resource import Resource
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.models.task import Task
from db_repo_module.models.user import User
from db_repo_module.models.user_role import UserRole
from db_repo_module.models.product_analytics import ProductAnalytics
from db_repo_module.models.session import Session
from db_repo_module.models.config import Config
from db_repo_module.models.dynamic_query_yaml import DynamicQueryYaml
from db_repo_module.models.model_schema import ModelSchema
from db_repo_module.models.workflow_pipeline import WorkflowPipeline
from db_repo_module.models.workflow_runs import WorkflowRuns
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.image_search_models import (
    ReferenceImageFeatures,
    SIFTFeatures,
)
from db_repo_module.models.ikb_models import ImageKnowledgeBase
from db_repo_module.models.namespace import Namespace
from db_repo_module.models.agent import Agent
from db_repo_module.models.workflow import Workflow
from db_repo_module.models.api_services import ApiServices
from dependency_injector import containers
from dependency_injector import providers


class DatabaseModuleContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])

    db_config = providers.Factory(
        DatabaseConfig,
        username=config.database.username,
        password=config.database.password,
        host=config.database.host,
        port=config.database.port,
        db_name=config.database.db_name,
    )

    db_client = providers.Singleton(DatabaseClient, db_config=db_config)

    email_repository = providers.Singleton(
        SQLAlchemyRepository[Email], model=Email, db_client=db_client
    )

    oauth_credential_repository = providers.Singleton(
        SQLAlchemyRepository[OAuthCredential],
        model=OAuthCredential,
        db_client=db_client,
    )

    user_repository = providers.Singleton(
        SQLAlchemyRepository[User], model=User, db_client=db_client
    )

    task_repository = providers.Singleton(
        SQLAlchemyRepository[Task], model=Task, db_client=db_client
    )

    notification_repository = providers.Singleton(
        SQLAlchemyRepository[Notification], model=Notification, db_client=db_client
    )
    notification_user_repository = providers.Singleton(
        SQLAlchemyRepository[NotificationUser],
        model=NotificationUser,
        db_client=db_client,
    )
    resource_repository = providers.Singleton(
        SQLAlchemyRepository[Resource],
        model=Resource,
        db_client=db_client,
    )
    resource_role_repository = providers.Singleton(
        SQLAlchemyRepository[RoleResource],
        model=RoleResource,
        db_client=db_client,
    )
    user_resource_repository = providers.Singleton(
        SQLAlchemyRepository[UserRole],
        model=UserRole,
        db_client=db_client,
    )

    cache_manager = providers.Singleton(
        CacheManager, namespace=config.env_config.app_name
    )

    knowledge_base_repository = providers.Singleton(
        SQLAlchemyRepository[KnowledgeBase],
        model=KnowledgeBase,
        db_client=db_client,
    )

    knowledge_base_documents_repository = providers.Singleton(
        SQLAlchemyRepository[KnowledgeBaseDocuments],
        model=KnowledgeBaseDocuments,
        db_client=db_client,
    )

    knowledge_base_embeddings_repository = providers.Singleton(
        SQLAlchemyRepository[KnowledgeBaseEmbeddings],
        model=KnowledgeBaseEmbeddings,
        db_client=db_client,
    )

    kb_inference_repository = providers.Singleton(
        SQLAlchemyRepository[KnowledgeBaseInferences],
        model=KnowledgeBaseInferences,
        db_client=db_client,
    )

    auth_secrets_repository = providers.Singleton(
        SQLAlchemyRepository[AuthSecrets],
        model=AuthSecrets,
        db_client=db_client,
    )

    product_analytics_repository = providers.Singleton(
        SQLAlchemyRepository[ProductAnalytics],
        model=ProductAnalytics,
        db_client=db_client,
    )

    session_repository = providers.Singleton(
        SQLAlchemyRepository[Session],
        model=Session,
        db_client=db_client,
    )

    config_repository = providers.Singleton(
        SQLAlchemyRepository[Config],
        model=Config,
        db_client=db_client,
    )

    dynamic_query_repository = providers.Singleton(
        SQLAlchemyRepository[DynamicQueryYaml],
        model=DynamicQueryYaml,
        db_client=db_client,
    )

    model_inference_repository = providers.Singleton(
        SQLAlchemyRepository[ModelSchema],
        model=ModelSchema,
        db_client=db_client,
    )

    ikb_repository = providers.Singleton(
        SQLAlchemyRepository[ImageKnowledgeBase],
        model=ImageKnowledgeBase,
        db_client=db_client,
    )

    reference_features_repository = providers.Singleton(
        SQLAlchemyRepository[ReferenceImageFeatures],
        model=ReferenceImageFeatures,
        db_client=db_client,
    )

    sift_features_repository = providers.Singleton(
        SQLAlchemyRepository[SIFTFeatures],
        model=SIFTFeatures,
        db_client=db_client,
    )

    workflow_pipeline_repository = providers.Singleton(
        SQLAlchemyRepository[WorkflowPipeline],
        model=WorkflowPipeline,
        db_client=db_client,
    )

    workflow_runs_repository = providers.Singleton(
        SQLAlchemyRepository[WorkflowRuns],
        model=WorkflowRuns,
        db_client=db_client,
    )

    namespace_repository = providers.Singleton(
        SQLAlchemyRepository[Namespace],
        model=Namespace,
        db_client=db_client,
    )

    agent_repository = providers.Singleton(
        SQLAlchemyRepository[Agent],
        model=Agent,
        db_client=db_client,
    )

    workflow_repository = providers.Singleton(
        SQLAlchemyRepository[Workflow],
        model=Workflow,
        db_client=db_client,
    )

    api_services_repository = providers.Singleton(
        SQLAlchemyRepository[ApiServices],
        model=ApiServices,
        db_client=db_client,
    )

    datasource_repository = providers.Singleton(
        SQLAlchemyRepository[Datasource],
        model=Datasource,
        db_client=db_client,
    )
    knowledge_base_inference_repository = providers.Singleton(
        SQLAlchemyRepository[KnowledgeBaseInferences],
        model=KnowledgeBaseInferences,
        db_client=db_client,
    )
