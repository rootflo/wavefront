from db_repo_module.models.knowledge_base_documents import KnowledgeBaseDocuments
from db_repo_module.models.knowledge_base_embeddings import KnowledgeBaseEmbeddings
from db_repo_module.models.knowledge_bases import KnowledgeBase
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector import containers
from dependency_injector import providers
from knowledge_base_module.services.kb_rag_retrieve import KBRagResponse
from knowledge_base_module.services.image_rag_retrieve import ImageRagRetrieve


class KnowledgeBaseContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])
    db_client = providers.Dependency()
    ingestion_db_client = providers.Dependency()
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

    # Same table and model as knowledge_base_embeddings_repository above, but
    # bound to the isolated ingestion pool -- used only for the bulk insert in
    # store_embeddings, so that path can never starve the shared pool that
    # login/search/everything else depends on.
    knowledge_base_embeddings_write_repository = providers.Singleton(
        SQLAlchemyRepository[KnowledgeBaseEmbeddings],
        model=KnowledgeBaseEmbeddings,
        db_client=ingestion_db_client,
    )

    knowledge_base = providers.Singleton(KnowledgeBase)

    knowledge_base_retrieve = providers.Singleton(
        KBRagResponse,
        knowledge_base_documents_repository,
        knowledge_base_embeddings_repository,
        inference_url=config.model.inference_service_url,
    )

    knowledge_base_embeddings_repository = providers.Singleton(
        SQLAlchemyRepository[KnowledgeBaseEmbeddings],
        model=KnowledgeBaseEmbeddings,
        db_client=db_client,
    )

    cloud_storage = cloud_storage_manager
    message_queue = rag_queue

    image_knowledge_base_retrieve = providers.Singleton(
        ImageRagRetrieve,
        knowledge_base_embeddings_repository,
    )
