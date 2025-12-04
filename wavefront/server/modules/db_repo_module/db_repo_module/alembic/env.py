import os

from alembic import context
from db_repo_module.database.base import Base
from db_repo_module.models.documents import Document
from db_repo_module.models.email import Email
from db_repo_module.models.kb_inferences import KnowledgeBaseInferences
from db_repo_module.models.knowledge_base_documents import KnowledgeBaseDocuments
from db_repo_module.models.knowledge_base_embeddings import KnowledgeBaseEmbeddings
from db_repo_module.models.knowledge_bases import KnowledgeBase
from db_repo_module.models.notification_users import NotificationUser
from db_repo_module.models.notifications import Notification
from db_repo_module.models.oauth_credential import OAuthCredential
from db_repo_module.models.resource import Resource
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.models.saml_config import SAMLConfig
from db_repo_module.models.session import Session
from db_repo_module.models.task import Task
from db_repo_module.models.team import Team
from db_repo_module.models.user import User
from db_repo_module.models.user_role import UserRole
from db_repo_module.models.datasource import Datasource
from db_repo_module.models.model_schema import ModelSchema
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from db_repo_module.models.image_search_models import (
    ReferenceImageFeatures,
    SIFTFeatures,
)
from db_repo_module.models.ikb_models import ImageKnowledgeBase
from db_repo_module.models.telephony_config import TelephonyConfig
from db_repo_module.models.tts_config import TtsConfig
from db_repo_module.models.stt_config import SttConfig
from db_repo_module.models.voice_agent import VoiceAgent
from db_repo_module.models.message_processors import MessageProcessors
from dotenv import load_dotenv
from sqlalchemy import engine_from_config
from sqlalchemy import pool

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config


# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
models = [
    Document,
    Email,
    OAuthCredential,
    Role,
    SAMLConfig,
    Task,
    Team,
    Session,
    User,
    Notification,
    NotificationUser,
    Resource,
    RoleResource,
    UserRole,
    KnowledgeBase,
    KnowledgeBaseDocuments,
    KnowledgeBaseEmbeddings,
    KnowledgeBaseInferences,
    Datasource,
    ModelSchema,
    LlmInferenceConfig,
    ReferenceImageFeatures,
    SIFTFeatures,
    ImageKnowledgeBase,
    TelephonyConfig,
    TtsConfig,
    SttConfig,
    VoiceAgent,
    MessageProcessors,
]
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

load_dotenv()
db_user_name = os.getenv('DB_USERNAME')
db_password = os.getenv('DB_PASSWORD')
db_host = os.getenv('DB_HOST')
db_port = os.getenv('DB_PORT')
db_name = os.getenv('DB_NAME')

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
