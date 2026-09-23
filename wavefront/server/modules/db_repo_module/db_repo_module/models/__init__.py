"""Every mapped model, imported so that ``Base.metadata`` is always complete.

SQLAlchemy only knows about a table once the module defining it has been
imported. Anything that works off the whole schema -- Alembic autogenerate, and
``create_all`` in the test harness -- therefore has to import every model first
or it fails on the first unresolved cross-module foreign key. Importing this
package is how that is guaranteed; add new models here when you create them.
"""

from db_repo_module.models.agent import Agent
from db_repo_module.models.agent_version import AgentVersion
from db_repo_module.models.agentic_configuration import AgenticConfiguration
from db_repo_module.models.agentic_trigger import AgenticTrigger
from db_repo_module.models.agentic_trigger_event import AgenticTriggerEvent
from db_repo_module.models.api_services import ApiServices
from db_repo_module.models.async_agentic_execution import AsyncAgenticExecution
from db_repo_module.models.auth_secrets import AuthSecrets
from db_repo_module.models.authenticator import Authenticator
from db_repo_module.models.chat_message import ChatMessage
from db_repo_module.models.chat_session import ChatSession
from db_repo_module.models.chatbot import Chatbot
from db_repo_module.models.config import Config
from db_repo_module.models.datasource import Datasource
from db_repo_module.models.datasource_audit_log import DatasourceAuditLog
from db_repo_module.models.documents import Document
from db_repo_module.models.dynamic_query_yaml import DynamicQueryYaml
from db_repo_module.models.email_connection import EmailConnection
from db_repo_module.models.ikb_models import ImageKnowledgeBase
from db_repo_module.models.image_search_models import ReferenceImageFeatures
from db_repo_module.models.image_search_models import SIFTFeatures
from db_repo_module.models.kb_inferences import KnowledgeBaseInferences
from db_repo_module.models.knowledge_base_documents import KnowledgeBaseDocuments
from db_repo_module.models.knowledge_base_embeddings import KnowledgeBaseEmbeddings
from db_repo_module.models.knowledge_bases import KnowledgeBase
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from db_repo_module.models.message_processors import MessageProcessors
from db_repo_module.models.model_schema import ModelSchema
from db_repo_module.models.namespace import Namespace
from db_repo_module.models.notification_users import NotificationUser
from db_repo_module.models.notifications import Notification
from db_repo_module.models.oauth_app import OAuthApp
from db_repo_module.models.product_analytics import ProductAnalytics
from db_repo_module.models.resource import Resource
from db_repo_module.models.resource import ResourceScope
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.models.saml_config import SAMLConfig
from db_repo_module.models.scheduled_job import ScheduledJob
from db_repo_module.models.scheduled_job_execution import ScheduledJobExecution
from db_repo_module.models.session import Session
from db_repo_module.models.stt_config import SttConfig
from db_repo_module.models.task import Task
from db_repo_module.models.team import Team
from db_repo_module.models.telephony_config import TelephonyConfig
from db_repo_module.models.tts_config import TtsConfig
from db_repo_module.models.user import User
from db_repo_module.models.user_group import UserGroup
from db_repo_module.models.user_group_member import UserGroupMember
from db_repo_module.models.user_group_role import UserGroupRole
from db_repo_module.models.user_role import UserRole
from db_repo_module.models.voice_agent import VoiceAgent
from db_repo_module.models.voice_agent_tool import ToolType
from db_repo_module.models.voice_agent_tool import VoiceAgentTool
from db_repo_module.models.voice_agent_tool_association import (
    VoiceAgentToolAssociation,
)
from db_repo_module.models.workflow import Workflow
from db_repo_module.models.workflow_pipeline import WorkflowPipeline
from db_repo_module.models.workflow_runs import WorkflowRuns
from db_repo_module.models.workflow_version import WorkflowVersion

__all__ = [
    'Agent',
    'AgentVersion',
    'AgenticConfiguration',
    'AgenticTrigger',
    'AgenticTriggerEvent',
    'ApiServices',
    'AsyncAgenticExecution',
    'AuthSecrets',
    'Authenticator',
    'ChatMessage',
    'ChatSession',
    'Chatbot',
    'Config',
    'Datasource',
    'DatasourceAuditLog',
    'Document',
    'DynamicQueryYaml',
    'EmailConnection',
    'ImageKnowledgeBase',
    'KnowledgeBase',
    'KnowledgeBaseDocuments',
    'KnowledgeBaseEmbeddings',
    'KnowledgeBaseInferences',
    'LlmInferenceConfig',
    'MessageProcessors',
    'ModelSchema',
    'Namespace',
    'Notification',
    'NotificationUser',
    'OAuthApp',
    'ProductAnalytics',
    'ReferenceImageFeatures',
    'Resource',
    'ResourceScope',
    'Role',
    'RoleResource',
    'SAMLConfig',
    'SIFTFeatures',
    'ScheduledJob',
    'ScheduledJobExecution',
    'Session',
    'SttConfig',
    'Task',
    'Team',
    'TelephonyConfig',
    'ToolType',
    'TtsConfig',
    'User',
    'UserGroup',
    'UserGroupMember',
    'UserGroupRole',
    'UserRole',
    'VoiceAgent',
    'VoiceAgentTool',
    'VoiceAgentToolAssociation',
    'Workflow',
    'WorkflowPipeline',
    'WorkflowRuns',
    'WorkflowVersion',
]
