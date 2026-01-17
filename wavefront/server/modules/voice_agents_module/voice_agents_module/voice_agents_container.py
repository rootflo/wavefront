from dependency_injector import containers, providers

from db_repo_module.models.telephony_config import TelephonyConfig
from db_repo_module.models.tts_config import TtsConfig
from db_repo_module.models.stt_config import SttConfig
from db_repo_module.models.voice_agent import VoiceAgent
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from db_repo_module.models.voice_agent_tool import VoiceAgentTool
from db_repo_module.models.voice_agent_tool_association import VoiceAgentToolAssociation
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from voice_agents_module.services.telephony_config_service import TelephonyConfigService
from voice_agents_module.services.tts_config_service import TtsConfigService
from voice_agents_module.services.stt_config_service import SttConfigService
from voice_agents_module.services.voice_agent_service import VoiceAgentService
from voice_agents_module.services.twilio_service import TwilioService
from voice_agents_module.services.tts_generator_service import TTSGeneratorService
from voice_agents_module.services.tool_service import ToolService


class VoiceAgentsContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])

    # External dependencies
    db_client = providers.Dependency()
    cache_manager = providers.Dependency()
    cloud_storage_manager = providers.Dependency()

    # Repositories
    telephony_config_repository = providers.Singleton(
        SQLAlchemyRepository[TelephonyConfig],
        model=TelephonyConfig,
        db_client=db_client,
    )

    tts_config_repository = providers.Singleton(
        SQLAlchemyRepository[TtsConfig],
        model=TtsConfig,
        db_client=db_client,
    )

    stt_config_repository = providers.Singleton(
        SQLAlchemyRepository[SttConfig],
        model=SttConfig,
        db_client=db_client,
    )

    llm_config_repository = providers.Singleton(
        SQLAlchemyRepository[LlmInferenceConfig],
        model=LlmInferenceConfig,
        db_client=db_client,
    )

    voice_agent_repository = providers.Singleton(
        SQLAlchemyRepository[VoiceAgent],
        model=VoiceAgent,
        db_client=db_client,
    )

    tool_repository = providers.Singleton(
        SQLAlchemyRepository[VoiceAgentTool],
        model=VoiceAgentTool,
        db_client=db_client,
    )

    tool_association_repository = providers.Singleton(
        SQLAlchemyRepository[VoiceAgentToolAssociation],
        model=VoiceAgentToolAssociation,
        db_client=db_client,
    )

    # Services
    telephony_config_service = providers.Singleton(
        TelephonyConfigService,
        telephony_config_repository=telephony_config_repository,
        cache_manager=cache_manager,
    )

    tts_config_service = providers.Singleton(
        TtsConfigService,
        tts_config_repository=tts_config_repository,
        cache_manager=cache_manager,
    )

    stt_config_service = providers.Singleton(
        SttConfigService,
        stt_config_repository=stt_config_repository,
        cache_manager=cache_manager,
    )

    tts_generator_service = providers.Singleton(
        TTSGeneratorService,
    )

    voice_agent_service = providers.Singleton(
        VoiceAgentService,
        voice_agent_repository=voice_agent_repository,
        telephony_config_service=telephony_config_service,
        tts_config_service=tts_config_service,
        stt_config_service=stt_config_service,
        llm_config_repository=llm_config_repository,
        cache_manager=cache_manager,
        tts_generator_service=tts_generator_service,
        cloud_storage_manager=cloud_storage_manager,
        voice_agent_bucket=config.voice_agents.voice_agent_bucket,
    )

    twilio_service = providers.Singleton(
        TwilioService,
        call_processing_base_url=config.voice_agents.call_processing_base_url,
    )

    tool_service = providers.Singleton(
        ToolService,
        tool_repository=tool_repository,
        tool_association_repository=tool_association_repository,
        cache_manager=cache_manager,
    )
