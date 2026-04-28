from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.product_analytics import ProductAnalytics
from db_repo_module.db_repo_container import DatabaseModuleContainer
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import Depends
from datetime import date
import os
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

    async def get_login_stats(self, start_date: date, end_date: date) -> list[dict]:
        excluded_emails_raw = os.getenv(
            'PRODUCT_ANALYTICS_EXCLUDED_EMAILS',
            '',
        )
        excluded_emails = [
            e.strip() for e in excluded_emails_raw.split(',') if e.strip()
        ]

        query = """
WITH login_events AS (
    SELECT
        u.email,
        pa.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' AS created_at_ist
    FROM product_analytics pa
    JOIN "user" u ON u.id::text = pa.user_id
    WHERE
        pa.event_name = 'user_login'
        AND u.deleted = FALSE
        AND u.email <> ALL(CAST(:excluded_emails AS text[]))
        AND (pa.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata')::date
            BETWEEN :start_date AND :end_date
)

SELECT
    u.email,
    COALESCE(COUNT(l.created_at_ist), 0)                    AS total_login_count,
    COALESCE(COUNT(DISTINCT l.created_at_ist::date), 0)     AS unique_login_days
FROM "user" u
LEFT JOIN login_events l ON u.email = l.email
WHERE
    u.deleted = FALSE
    AND u.email <> ALL(CAST(:excluded_emails AS text[]))
GROUP BY u.email
ORDER BY u.email
"""

        return await self.product_analysis_repository.execute_query(
            query=query,
            params={
                'start_date': start_date,
                'end_date': end_date,
                'excluded_emails': excluded_emails,
            },
        )