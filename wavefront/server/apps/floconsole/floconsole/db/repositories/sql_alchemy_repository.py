from typing import Any, Generic, Type, TypeVar

from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import insert
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.sql import text

from ..base import Base
from ..connection import DatabaseClient

T = TypeVar('T', bound=Base)  # type: ignore


class SQLAlchemyRepository(Generic[T]):
    def __init__(self, model: Type[T], db_client: DatabaseClient):
        """
        Initialize the repository with a specific model.

        :param model: The SQLAlchemy model class (subclass of Base).
        """
        self.model: Type[T] = model
        self.session: async_sessionmaker[AsyncSession] = db_client.session

    async def create(self, **kwargs) -> T:
        """
        Create a new record in the database.

        :param kwargs: The fields and their values to create the record.
        :return: The created instance of the model.
        """
        async with self.session() as session:
            session: AsyncSession
            instance = self.model(**kwargs)
            session.add(instance)
            await session.commit()
            await session.refresh(instance)

            return instance

    async def create_all(
        self,
        records: list[T],
        replace: bool = False,
        session: AsyncSession | None = None,
    ):
        """
        Create new records in the database.

        :param records: List of records
        :param replace: Replace a record if it already exists. Default: False
        :param session: Optional session for transaction management
        :return: The created instances of the model.
        """
        model_instances = []
        for data in records:
            model_instances.append(data)

        if session:
            for instance in model_instances:
                await session.merge(instance) if replace else session.add(instance)
            return records
        else:
            async with self.session() as session:
                session: AsyncSession
                for instance in model_instances:
                    await session.merge(instance) if replace else session.add(instance)
                await session.commit()
                return records

    async def find(self, limit: int = 100, **filters) -> list[T]:
        """
        Find all records in the database matching the given filters.

        :param filters: The filters to apply to the query.
        :return: A list of matching model instances.
        """
        if 'session' in filters and isinstance(filters['session'], AsyncSession):
            session = filters['session']
            del filters['session']
            query = select(self.model)
            for key, value in filters.items():
                if isinstance(value, list):
                    query = query.where(getattr(self.model, key).in_(value))
                else:
                    query = query.where(getattr(self.model, key) == value)
            query = query.limit(limit)
            result = await session.scalars(query)
            return list(result.all())

        async with self.session() as session:
            session: AsyncSession
            query = select(self.model)
            for key, value in filters.items():
                if isinstance(value, list):
                    query = query.where(getattr(self.model, key).in_(value))
                else:
                    query = query.where(getattr(self.model, key) == value)
            query = query.limit(limit)
            result = await session.scalars(query)
            return list(result.all())

    async def find_one(self, **filters) -> T | None:
        """
        Find the first record in the database matching the given filters.

        :param filters: The filters to apply to the query.
        :return: The first matching model instance, or None if no match is found.
        """
        async with self.session() as session:
            session: AsyncSession
            query = select(self.model)
            for key, value in filters.items():
                query = query.where(getattr(self.model, key) == value)
            return await session.scalar(query)

    async def find_one_and_update(
        self, filters: dict[str, Any], refresh: bool = False, **update_data
    ) -> T | None:
        """
        Find the first record in the database matching the given filters, and update it with the provided data.

        :param filters: The filters to apply to the query.
        :param update_data: The data to update the record with.
        :return: The updated model instance, or None if no match is found.
        """
        async with self.session() as session:
            session: AsyncSession
            query = select(self.model)
            for key, value in filters.items():
                query = query.where(getattr(self.model, key) == value)
            instance = await session.scalar(query)
            if instance:
                for key, value in update_data.items():
                    setattr(instance, key, value)
                await session.commit()
                if refresh:
                    await session.refresh(
                        instance
                    )  # Refresh to ensure object is properly attached
                return instance
            else:
                return None

    async def delete_all(self, **filters) -> None:
        """
        Delete all records in the database matching the given filters.

        :param filters: The filters to apply to the query.
        """
        async with self.session() as session:
            session: AsyncSession
            query = delete(self.model)
            for key, value in filters.items():
                query = query.where(getattr(self.model, key) == value)
            await session.execute(query)
            await session.commit()

    async def check_empty(self) -> bool:
        """
        Check if the database table is empty.

        :return: True if the table is empty, False otherwise.
        """
        async with self.session() as session:
            session: AsyncSession
            count = await session.scalar(select(func.count()).select_from(self.model))
            return count == 0

    async def count(self, **filters) -> int:
        """
        retrieve all the data from the table
        :return the count after applying the filters
        """
        async with self.session() as session:
            session: AsyncSession
            query = select(func.count()).select_from(self.model)
            for key, value in filters.items():
                query = query.where(getattr(self.model, key) == value)
            count = await session.scalar(query)
            return int(count or 0)

    async def execute_query(self, query: str, params={}, model_class=None) -> list:
        """
        Execute a raw SQL query asynchronously and return the results.

        :param query: The raw SQL string.
        :return: A list of matching records.
        """
        async with self.session() as session:
            session: AsyncSession
            result = await session.execute(text(query), params)
            columns = result.keys()
            rows = [dict(zip(columns, row)) for row in result.all()]
            if model_class:
                return [model_class(**row) for row in rows]
            return rows

    async def upsert(self, filters: dict[str, Any], **update_values):
        """
        Find the first record in the database matching the given filters
        if the record exists it will update the record with specified filters
        otherwise it will create an record with filters and update_values
        """
        async with self.session() as session:
            session: AsyncSession
            query = select(self.model).filter_by(**filters)
            result = await session.execute(query)
            existing_count = result.scalar_one_or_none()
            if existing_count:
                stmt = (
                    update(self.model)
                    .where(
                        *(
                            getattr(self.model, key) == val
                            for key, val in filters.items()
                        )
                    )
                    .values(**update_values)
                )
                await session.execute(stmt)
            else:
                stmt = insert(self.model).values({**filters, **update_values})
                await session.execute(stmt)
            await session.commit()
