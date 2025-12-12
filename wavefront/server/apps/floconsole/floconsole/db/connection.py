from dataclasses import dataclass
import os

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine


@dataclass
class DatabaseConfig:
    username: str
    password: str
    host: str
    port: str
    db_name: str


class DatabaseClient:
    def __init__(self, db_config: DatabaseConfig) -> None:
        self.db_config = db_config
        self._engine = create_async_engine(
            f'postgresql+psycopg://{db_config.username}:{db_config.password}@{db_config.host}:{db_config.port}/{db_config.db_name}'
        )
        self.session = async_sessionmaker(autocommit=False, bind=self._engine)

    async def close(self):
        if self._engine is None:
            raise Exception('DatabaseClient is not initialized')
        await self._engine.dispose()

        self._engine = None
        self.session = None

    async def connect(self) -> None:
        if self._engine is None:
            # logger.error('Error database connection ..')
            raise Exception('DatabaseClient is not initialized')

    def run_migration(self):
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        alembic = os.path.join(current_script_dir, 'alembic.ini')
        absolute_file_path = os.path.abspath(alembic)
        alembic_config = Config(absolute_file_path)
        command.upgrade(alembic_config, 'head')
