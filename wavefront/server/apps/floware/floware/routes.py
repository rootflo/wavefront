from fastapi import FastAPI

from agents_module.controllers.agent_controller import agents_router
from agents_module.controllers.async_inference_controller import async_router
from agents_module.controllers.namespace_controller import namespace_router
from agents_module.controllers.workflow_controller import workflows_router
from agents_module.controllers.workflow_pipeline_controller import (
    workflow_pipeline_router,
)
from agents_module.controllers.workflow_runs import workflow_runs_router
from auth_module.controllers.hmac_controller import hmac_router
from auth_module.controllers.superset_controller import superset_controller
from chatbots_module.controllers.chatbot_controller import chatbot_router
from chatbots_module.controllers.chat_session_controller import chat_session_router
from floware.controllers.config_controller import config_router
from floware.controllers.notification_controller import notification_router
from floware.controllers.scheduled_job_controller import scheduled_job_router
from gold_module.controllers.router import gold_router
from guardrails_module.controllers.guardrails_controller import guardrails_router
from inference_module.controllers.inference_controller import inference_router
from knowledge_base_module.controllers.knowledge_base_controller import (
    knowledge_base_router,
)
from knowledge_base_module.controllers.knowledge_base_document_controller import (
    kb_document_router,
)
from knowledge_base_module.controllers.rag_retreival_controller import (
    rag_retrieval_router,
)
from llm_inference_config_module.controllers.inference_proxy_controller import (
    inference_proxy_router,
)
from llm_inference_config_module.controllers.llm_inference_config_controller import (
    llm_inference_config_router,
)
from plugins_module.controllers.authenticator_controller import authenticator_router
from plugins_module.controllers.cloud_storage_controller import cloud_storage_router
from plugins_module.controllers.configuration_controller import configuration_router
from plugins_module.controllers.datasource_audit_controller import (
    datasource_audit_router,
)
from plugins_module.controllers.datasource_controller import datasource_router
from plugins_module.controllers.email_connection_controller import (
    email_connection_router,
)
from plugins_module.controllers.oauth_app_controller import (
    oauth_app_router,
)
from plugins_module.controllers.message_processor_controller import (
    message_processor_router,
)
from product_analysis_module.controllers.product_anaysis_controllers import (
    product_analysis_router,
)
from tools_module.controllers.tools_controller import tools_router
from triggers_module.controllers.trigger_controller import trigger_router
from user_management_module.router import user_management_router
from voice_agents_module.controllers.stt_config_controller import stt_config_router
from voice_agents_module.controllers.telephony_config_controller import (
    telephony_config_router,
)
from voice_agents_module.controllers.tool_controller import tool_router
from voice_agents_module.controllers.tts_config_controller import tts_config_router
from voice_agents_module.controllers.voice_agent_controller import voice_agent_router

FLOWARE_PREFIX = '/floware'

FLOWARE_ROUTERS = [
    agents_router,
    async_router,
    authenticator_router,
    chatbot_router,
    chat_session_router,
    cloud_storage_router,
    config_router,
    configuration_router,
    datasource_audit_router,
    datasource_router,
    email_connection_router,
    oauth_app_router,
    gold_router,
    guardrails_router,
    hmac_router,
    inference_proxy_router,
    inference_router,
    kb_document_router,
    knowledge_base_router,
    llm_inference_config_router,
    message_processor_router,
    namespace_router,
    notification_router,
    product_analysis_router,
    rag_retrieval_router,
    scheduled_job_router,
    stt_config_router,
    superset_controller,
    telephony_config_router,
    tool_router,
    tools_router,
    trigger_router,
    tts_config_router,
    user_management_router,
    voice_agent_router,
    workflow_pipeline_router,
    workflow_runs_router,
    workflows_router,
]


def include_routers(app: FastAPI) -> None:
    for router in FLOWARE_ROUTERS:
        app.include_router(router, prefix=FLOWARE_PREFIX)
