import http from '@app/lib/axios';
import { AxiosInstance } from 'axios';
import { AgentService } from './agent-service';
import { ApiServiceService } from './api-service-service';
import { AppService } from './app-service';
import { AuthenticatorService } from './authenticator-service';
import { ConsoleAuthService } from './console-auth-service';
import { DataPipelineService } from './data-pipeline-service';
import { DatasourcesService } from './datasources-service';
import { KnowledgeBaseService } from './knowledge-base-service';
import { LLMInferenceService } from './llm-inference-service';
import { MessageProcessorService } from './message-processor-service';
import { ModelInferenceService } from './model-inference-service';
import { NamespaceService } from './namespace-service';
import { SttConfigService } from './stt-config-service';
import { TelephonyConfigService } from './telephony-config-service';
import { ToolService } from './tool-service';
import { TtsConfigService } from './tts-config-service';
import { UserService } from './user-service';
import { VoiceAgentService } from './voice-agent-service';
import { WorkflowService } from './workflow-service';

class FloConsoleService {
  private http: AxiosInstance;

  constructor() {
    this.http = http;
  }

  get agentService() {
    return new AgentService(this.http);
  }

  get apiServiceService() {
    return new ApiServiceService(this.http);
  }

  get appService() {
    return new AppService(this.http);
  }

  get authenticatorService() {
    return new AuthenticatorService(this.http);
  }

  get consoleAuthService() {
    return new ConsoleAuthService(this.http);
  }

  get dataPipelineService() {
    return new DataPipelineService(this.http);
  }

  get datasourcesService() {
    return new DatasourcesService(this.http);
  }

  get knowledgeBaseService() {
    return new KnowledgeBaseService(this.http);
  }

  get llmInferenceService() {
    return new LLMInferenceService(this.http);
  }

  get messageProcessorService() {
    return new MessageProcessorService(this.http);
  }

  get modelInferenceService() {
    return new ModelInferenceService(this.http);
  }

  get namespaceService() {
    return new NamespaceService(this.http);
  }

  get sttConfigService() {
    return new SttConfigService(this.http);
  }

  get telephonyConfigService() {
    return new TelephonyConfigService(this.http);
  }

  get toolService() {
    return new ToolService(this.http);
  }

  get ttsConfigService() {
    return new TtsConfigService(this.http);
  }

  get userService() {
    return new UserService(this.http);
  }

  get voiceAgentService() {
    return new VoiceAgentService(this.http);
  }

  get workflowService() {
    return new WorkflowService(this.http);
  }
}

const floConsoleService = new FloConsoleService();

export default floConsoleService;
