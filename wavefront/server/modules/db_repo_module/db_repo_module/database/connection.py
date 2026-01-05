from dataclasses import dataclass
from pathlib import Path

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
        self._session = None

    async def connect(self) -> None:
        if self._engine is None:
            raise Exception('DatabaseClient is not initialized')

        async with self._engine.begin() as connection:
            try:
                await connection.exec_driver_sql(
                    'CREATE EXTENSION IF NOT EXISTS vector;'
                )
            except Exception:
                await connection.rollback()
                raise

    def _get_alembic_config_path(self) -> Path:
        """Get the absolute path to the alembic.ini configuration file.

        Returns:
            Path: Absolute path to the alembic.ini file

        Raises:
            FileNotFoundError: If alembic.ini file is not found
        """
        current_file = Path(__file__)
        alembic_path = current_file.parent.parent / 'alembic.ini'

        if not alembic_path.exists():
            raise FileNotFoundError(
                f'Alembic configuration file not found at: {alembic_path}'
            )

        return alembic_path

    def run_migration(self, target_revision: str = 'head') -> None:
        """Run database migrations using Alembic.

        Args:
            target_revision: The target revision to migrate to. Defaults to 'head'.

        Raises:
            FileNotFoundError: If alembic.ini file is not found
            Exception: If migration fails
        """
        try:
            alembic_config_path = self._get_alembic_config_path()
            alembic_config = Config(str(alembic_config_path))
            command.upgrade(alembic_config, target_revision)
        except FileNotFoundError as e:
            raise FileNotFoundError(f'Migration failed: {e}')
        except Exception as e:
            raise Exception(f'Migration failed with error: {e}')
