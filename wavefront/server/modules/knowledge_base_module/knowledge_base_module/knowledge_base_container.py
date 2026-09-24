from db_repo_module.models.kb_inferences import KnowledgeBaseInferences
from db_repo_module.models.knowledge_base_documents import KnowledgeBaseDocuments
from db_repo_module.models.knowledge_base_embeddings import KnowledgeBaseEmbeddings
from db_repo_module.models.knowledge_bases import KnowledgeBase
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector import containers
from dependency_injector import providers
from knowledge_base_module.services.kb_rag_retrieve import KBRagResponse
from knowledge_base_module.services.kb_rag_storage import KBRagStorage
from knowledge_base_module.services.image_rag_retrieve import ImageRagRetrieve


class KnowledgeBaseContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])
    db_client = providers.Dependency()
    cache_manager = providers.Dependency()
    cloud_storage_manager = providers.Dependency()
    rag_queue = providers.Dependency()

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

    llm_config_repository = providers.Singleton(
        SQLAlchemyRepository[LlmInferenceConfig],
        model=LlmInferenceConfig,
        db_client=db_client,
    )

    email_rag_service = providers.Factory(
        KBRagStorage, embedding_url=config.embedding_url.embedding_service_url
    )

    knowledge_base = providers.Singleton(KnowledgeBase)

    knowledge_base_retrieve = providers.Singleton(
        KBRagResponse,
        knowledge_base_documents_repository,
        knowledge_base_embeddings_repository,
        embedding_url=config.embedding_url.embedding_service_url,
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

    # Alias kept for existing Provide[...] wiring.
    cloud_storage = cloud_storage_manager
    message_queue = rag_queue

    image_knowledge_base_retrieve = providers.Singleton(
        ImageRagRetrieve,
        knowledge_base_embeddings_repository,
    )
