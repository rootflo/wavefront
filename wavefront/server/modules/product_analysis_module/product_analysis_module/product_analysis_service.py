from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.product_analytics import ProductAnalytics
from db_repo_module.models.user import User
from db_repo_module.models.user_role import UserRole
from db_repo_module.db_repo_container import DatabaseModuleContainer
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import Depends
from datetime import date, datetime, time
import os
from product_analysis_module.models.product_analysis import ProductAnalysis
from sqlalchemy import Date, String, cast, func, select


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

    def _user_filters(self, role_id: str | None = None) -> list:
        excluded_emails_raw = os.getenv(
            'PRODUCT_ANALYTICS_EXCLUDED_EMAILS',
            '',
        )
        excluded_emails = [
            e.strip() for e in excluded_emails_raw.split(',') if e.strip()
        ]
        user_filters = [User.deleted.is_(False)]
        if excluded_emails:
            user_filters.append(User.email.notin_(excluded_emails))
        if role_id:
            user_filters.append(
                User.id.in_(select(UserRole.user_id).where(UserRole.role_id == role_id))
            )
        return user_filters

    def _login_events_cte(self, start_date: date, end_date: date, user_filters: list):
        range_start = datetime.combine(start_date, time.min)
        range_end = datetime.combine(end_date, time.min)
        return (
            select(
                User.email.label('email'),
                ProductAnalytics.created_at.label('created_at'),
            )
            .select_from(ProductAnalytics)
            .join(User, cast(User.id, String) == cast(ProductAnalytics.user_id, String))
            .where(
                ProductAnalytics.event_name == 'user_login',
                *user_filters,
                ProductAnalytics.created_at >= range_start,
                ProductAnalytics.created_at < range_end,
            )
            .cte('login_events')
        )

    async def get_login_stats(
        self,
        start_date: date,
        end_date: date,
        limit: int,
        offset: int,
        role_id: str | None = None,
    ) -> tuple[list[dict], int]:
        user_filters = self._user_filters(role_id)
        login_events = self._login_events_cte(start_date, end_date, user_filters)

        query = (
            select(
                User.email,
                func.coalesce(func.count(login_events.c.created_at), 0).label(
                    'total_login_count'
                ),
                func.coalesce(
                    func.count(func.distinct(cast(login_events.c.created_at, Date))),
                    0,
                ).label('unique_login_days'),
            )
            .select_from(User)
            .outerjoin(login_events, User.email == login_events.c.email)
            .where(*user_filters)
            .group_by(User.email)
            .order_by(User.email)
            .offset(offset)
            .limit(limit)
        )
        count_query = (
            select(func.count().label('total')).select_from(User).where(*user_filters)
        )

        login_stats = await self.product_analysis_repository.execute_query(query=query)
        count_rows = await self.product_analysis_repository.execute_query(
            query=count_query
        )
        total = count_rows[0]['total'] if count_rows else 0
        return login_stats, total

    async def get_login_stats_summary(
        self,
        start_date: date,
        end_date: date,
        role_id: str | None = None,
    ) -> dict:
        user_filters = self._user_filters(role_id)
        login_events = self._login_events_cte(start_date, end_date, user_filters)
        unique_login_days = func.coalesce(
            func.count(func.distinct(cast(login_events.c.created_at, Date))),
            0,
        )
        user_stats = (
            select(unique_login_days.label('unique_login_days'))
            .select_from(User)
            .outerjoin(login_events, User.email == login_events.c.email)
            .where(*user_filters)
            .group_by(User.email)
            .cte('user_stats')
        )
        summary_query = select(
            func.count().label('total_users'),
            func.count()
            .filter(user_stats.c.unique_login_days > 1)
            .label('active_users'),
        ).select_from(user_stats)

        summary_rows = await self.product_analysis_repository.execute_query(
            query=summary_query
        )
        summary = summary_rows[0] if summary_rows else {}
        total_users = int(summary.get('total_users') or 0)
        active_users = int(summary.get('active_users') or 0)
        inactive_users = total_users - active_users
        adoption_rate = (
            round(active_users * 100 / total_users, 1) if total_users else 0.0
        )
        return {
            'total_users': total_users,
            'active_users': active_users,
            'inactive_users': inactive_users,
            'adoption_rate': adoption_rate,
        }
