from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.product_analytics import ProductAnalytics
from db_repo_module.db_repo_container import DatabaseModuleContainer
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import Depends
from product_analysis_module.models.product_analysis import ProductAnalysis


class ProductAnalysisService:
    @inject
    def __init__(
        self,
        product_analysis_repository: SQLAlchemyRepository[ProductAnalytics] = Depends(
            Provide[DatabaseModuleContainer.product_analytics_repository]
        ),
    ):
        self.product_analysis_repository = product_analysis_repository

    async def create_product_analysis(self, payload: ProductAnalysis):
        await self.product_analysis_repository.create(
            event_name=payload.event_name,
            type=payload.type,
            sub_type=payload.sub_type,
            category=payload.category,
            sub_category=payload.sub_category,
            action=payload.action,
            action_type=payload.action_type,
            page=payload.page,
            page_path=payload.page_path,
            matadata=payload.matadata,
            user_id=payload.user_id,
            session_id=payload.session_id,
            user_role=payload.user_role,
            created_at=payload.created_at,
        )

    async def get_product_analysis(self):
        return await self.product_analysis_repository.find()
