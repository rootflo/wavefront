from typing import List, Dict, Any
from tools_module.interfaces.tool_details_provider import ToolDetailsProvider
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.knowledge_bases import KnowledgeBase
from db_repo_module.models.kb_inferences import KnowledgeBaseInferences
from tools_module.models.tool_schemas import ToolExecutionDetails


class KnowledgeBaseToolDetailsProvider(ToolDetailsProvider):
    def __init__(
        self,
        knowledge_base_repository: SQLAlchemyRepository[KnowledgeBase],
        knowledge_base_inference_repository: SQLAlchemyRepository[
            KnowledgeBaseInferences
        ],
    ):
        self.knowledge_base_repository = knowledge_base_repository
        self.knowledge_base_inference_repository = knowledge_base_inference_repository

    def can_handle(self, category: str) -> bool:
        return (
            category == 'knowlegebase' or category == 'knowledgebase'
        )  # Handle both spellings if needed, but json says 'knowlegebase'

    async def get_tool_details(
        self, tool_metadata: Dict[str, Any]
    ) -> List[ToolExecutionDetails]:
        tool_details = []
        prefill_values = tool_metadata.get('prefill_values', [])

        if 'kb_id' in prefill_values and 'inference_id' in prefill_values:
            all_knowledge_bases = await self.knowledge_base_repository.find()
            all_knowledge_bases = [kb.to_dict() for kb in all_knowledge_bases]

            all_knoledge_base_inferences = (
                await self.knowledge_base_inference_repository.find()
            )
            all_knoledge_base_inferences = [
                inf.to_dict() for inf in all_knoledge_base_inferences
            ]

            for kb in all_knowledge_bases:
                kb_id = str(kb['id'])
                for inference in all_knoledge_base_inferences:
                    inference_kb_id = str(inference['knowledge_base_id'])
                    if inference_kb_id == kb_id:
                        tool_details.append(
                            ToolExecutionDetails(
                                name=tool_metadata['name'],
                                prefill_parameter_names=prefill_values,
                                prefilled_value={
                                    'kb_id': kb_id,
                                    'inference_id': str(inference['inference_id']),
                                },
                                resource_name=kb['name'],
                                required=tool_metadata.get('required', []),
                                parameters=tool_metadata['parameters'],
                                description=tool_metadata['description'],
                                category=tool_metadata['category'],
                            )
                        )
        else:
            tool_details.append(
                ToolExecutionDetails(
                    name=tool_metadata['name'],
                    resource_name='',
                    prefill_parameter_names=prefill_values,
                    prefilled_value={},
                    required=tool_metadata.get('required', []),
                    parameters=tool_metadata['parameters'],
                    description=tool_metadata['description'],
                    category=tool_metadata['category'],
                )
            )

        return tool_details
