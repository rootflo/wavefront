from knowledge_base_module.knowledge_base_container import KnowledgeBaseContainer

from db_repo_module.db_repo_container import DatabaseModuleContainer


async def querying_knowlegebase(
    kb_id: str,
    inference_id: str,
    question: str,
):
    # Your implementation here
    db_repo_container = DatabaseModuleContainer()
    db_client = db_repo_container.db_client
    cache_manager = db_repo_container.cache_manager
    knowlegebase_contaoiner = KnowledgeBaseContainer(
        db_client=db_client,
        cache_manager=cache_manager,
    )

    if not question:
        return 'Query should be not be empty'
    existing_kb = await knowlegebase_contaoiner.knowledge_base_repository().find_one(
        id=kb_id
    )
    if not existing_kb:
        return 'Knowledge Base with the mentioned id doesnt exist'
    existing_inference = (
        await knowlegebase_contaoiner.kb_inference_repository().find_one(
            knowledge_base_id=kb_id, inference_id=inference_id
        )
    )
    if not existing_inference:
        return 'Knowledge Base inference with the mentioned knowledge_base_id and inference_id doesnt exist'
    else:
        prompt = existing_inference.inference_content
        response = await knowlegebase_contaoiner.knowledge_base_retrieve().query(
            question,
            kb_id,
            prompt,
            None,
            None,
            None,
            None,
        )
        return response
