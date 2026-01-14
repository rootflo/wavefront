import os

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config
from sqlalchemy import pool

from floconsole.db.base import Base
from floconsole.db.models.user import User
from floconsole.db.models.session import Session
from floconsole.db.models.app import App
from floconsole.db.models.app_user import AppUser

# Load environment variables
load_dotenv()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Import all models here to ensure they're registered with Base.metadata
models = [
    User,
    Session,
    App,
    AppUser,
]

target_metadata = Base.metadata

# Get database URL from environment variables
db_user_name = os.getenv('CONSOLE_DB_USERNAME')
db_password = os.getenv('CONSOLE_DB_PASSWORD')
db_host = os.getenv('CONSOLE_DB_HOST')
db_port = os.getenv('CONSOLE_DB_PORT')
db_name = os.getenv('CONSOLE_DB_NAME')

db_url = f'postgresql://{db_user_name}:{db_password}@{db_host}:{db_port}/{db_name}'

config.set_main_option('sqlalchemy.url', db_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """

    url = config.get_main_option('sqlalchemy.url')
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
