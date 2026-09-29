# Wavefront AI Roadmap

This roadmap provides a comprehensive overview of the direction Wavefront AI is heading. It covers all major components of the platform: the Flo AI library, Wavefront Core middleware (Floware), the Control Panel (Flo Console), the CLI, and ecosystem tools.

The roadmap is organized by component and priority. We welcome community feedback and contributions!

---

## 📊 Current Release Scope

The current beta release includes the following features:

| Feature | Scope and limitations |
|---------|------------|
| **Datasource** | Connect to multiple datasources: Google BigQuery, AWS Redshift, PostgreSQL and SQL Server. Read and write through the resource API, or run and export YAML-defined dynamic queries. Datasource operations are audit logged. |
| **Agent** | Create agents in YAML from the console, with versioning, promotion and rollback. Run them synchronously or asynchronously on background workers. |
| **Workflow** | Create multi-agent workflows in YAML, reference saved agents, define agents inline or embed other workflows. Run them synchronously with streamed events, asynchronously, as pipelines, or on a schedule. |
| **Chatbot** | Configure chatbots as a system prompt bound to a model. Users get persistent sessions with streamed replies. Chatbots do not use tools yet. |
| **Voice Bots** | Inbound and outbound phone calls through Twilio, Exotel and Smartflo, with multiple languages, tools during calls and post-call evaluation. |
| **Knowledge Base** | Document ingestion, embeddings and hybrid vector and keyword retrieval on PostgreSQL (pgvector), plus image search. |
| **Triggers** | Start an agent or workflow from external events. Gmail is currently the only supported provider. |
| **API Service** | Create API services to connect to any backend service, with JSON and non-JSON payloads. Authentication is limited to API Key, Basic Auth and Bearer Token. |
| **Inference App** | Host custom PyTorch models. Support is limited to certain PyTorch models. This feature is fully `experimental`, and APIs are bound to change. |

## 🤖 Flo AI Library

The core agent building and orchestration framework. The following are planned or in progress for upcoming releases.

### Core Features

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Resume Work** | Functionality that lets agents resume from where they stopped, with state persistence | High | Yet to start | TBD |
| **LLM Router** | Intelligent model routing within agents, allowing dynamic LLM selection based on task complexity | High | Yet to start | TBD |
| **Parallel Router** | Execute independent tasks or agents in parallel for improved performance | High | Yet to start | TBD |
| **Agent Versioning** | Version control for agent configurations and workflows (provided by Wavefront Core) | Medium | ✅ Available | v1.1.6 |
| **Agent Templates** | Pre-built agent templates for common use cases (customer support, data analysis, etc.) | Medium | Yet to start | TBD |
| **Streaming Responses** | Real-time streaming of agent responses. Workflow event streaming is available; token streaming from tool-using agents is not yet supported | High | 🔄 In Progress | TBD |
| **Multi-modal Support** | Support for image, audio, and video inputs/outputs. Image and document inputs are available | Medium | Yet to start | TBD |
| **Custom Memory Backends** | Support for Redis, PostgreSQL, and other backends for agent memory | Medium | Yet to start | TBD |

### Observability & Debugging

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Recursion Control** | Expose parameters to limit recursions and define policies for recursion handling | High | ✅ Available | v1.1.9 |
| **Token Count Tracking** | Expose total tokens used by agent execution directly through session | High | ✅ Available | v1.1.6 |
| **Execution Time Metrics** | Detailed timing metrics for each agent and tool execution | Medium | ✅ Available | v1.1.6 |
| **Debug Mode** | Enhanced debugging mode with step-by-step execution logs | Medium | Yet to start | TBD |
| **Performance Profiling** | Identify bottlenecks in agent workflows | Medium | Yet to start | TBD |

### Advanced Orchestration

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Conditional Workflows** | Advanced conditional logic in YAML workflows | Medium | ✅ Available | v1.1.6 |
| **Loop & Iteration** | Support for loops and iterations in workflows | Medium | ✅ Available | v1.1.6 |
| **Error Recovery Strategies** | Configurable error recovery strategies per agent | High | ✅ Available | v1.1.6 |
| **Workflow Scheduling** | Schedule workflows to run at specific times or intervals | Low | ✅ Available | v1.1.6 |
| **LLM Router** | Route between workflow nodes using an LLM or a field value | Medium | ✅ Available | v1.1.6 |
| **Sub-workflows** | Reference and embed saved workflows inside other workflows | Medium | ✅ Available | v1.1.6 |

---

## 🏗️ Wavefront Core Middleware (a.k.a Floware)

The core middleware service that provides APIs, authentication, authorization, and data connectivity. Each application runs its own Floware deployment.

### Core Services

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **REST API** | Comprehensive REST API for agent management, workflow execution, and data access | High | ✅ Available | v1.1.6 |
| **Streaming** | Streamed workflow events and chat replies over HTTP | High | ✅ Available | v1.1.6 |
| **Agent Registry** | Centralized, versioned registry for agent and workflow definitions | High | ✅ Available | v1.1.6 |
| **Workflow Engine** | Server-side workflow execution engine | High | ✅ Available | v1.1.6 |
| **Async Execution** | Queue agent and workflow runs on background workers and poll their status | High | ✅ Available | v1.1.6 |
| **Chatbots & Sessions** | Chatbots with persistent per-user sessions and message history | High | ✅ Available | v1.1.6 |
| **Chatbot Tools** | Let chatbots call agents, workflows and datasource tools | High | Yet to start | TBD |
| **Triggers** | Start agents and workflows from external events (Gmail today) | Medium | ✅ Available | v1.1.6 |
| **Scheduled Jobs** | Run workflows on a schedule | Medium | ✅ Available | v1.1.6 |
| **API Gateway** | Unified API gateway with rate limiting and request routing | Medium | ✅ Available | v1.1.6 |

### Authentication & Authorization

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Email & Password** | Built-in sign-in with account lockout and reCAPTCHA protection | High | ✅ Available | v1.1.6 |
| **Google Auth Integration** | OAuth 2.0 integration with Google | High | ✅ Available | v1.1.6 |
| **Microsoft AD/Entra** | Enterprise SSO with Microsoft Entra (OAuth) and Microsoft ADFS | High | ✅ Available | v1.1.6 |
| **SAML 2.0 Support** | Standard SAML 2.0 authentication | High | Yet to start  | TBD |
| **LDAP Integration** | LDAP/Active Directory integration | Medium | Yet to start | TBD |
| **Auth0 Integration** | Auth0 SSO support | Medium | Yet to start | TBD |
| **Multi-Factor Authentication** | MFA support for enhanced security | Medium | Yet to start | TBD |
| **OAuth 2.0 Client Credentials** | OAuth 2.0 client credentials flow for service-to-service auth | Medium | Yet to start | TBD |

### RBAC & Permissions

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Agent-Level RBAC** | Fine-grained permissions for agent access and execution | High | Yet to start | Designing |
| **Data Source RBAC** | Granular permissions for data source access, including dynamic queries scoped to their datasource | High | 🔄 In Progress | Designing |
| **Role Management** | Create, update, and manage custom roles | High | ✅ Available | v1.1.6 |
| **Audit Logging for Access** | Comprehensive audit logs for all access attempts. Datasource operations are already audit logged | High | ✅ Available | v1.1.6 |

---

## 🎛️ Wavefront Control Panel (a.k.a Flo Console)

Unified frontend for configuring agents, workflows, AI models, guardrails, and RBAC. Flo Console also manages multiple applications, each backed by its own Floware deployment.

### Core Features

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Application Management** | Create and manage multiple applications and control who can access each one | High | ✅ Available | v1.1.6 |
| **Agent Management UI** | YAML interface for creating, editing, and managing agents | High | ✅ Available | v1.1.6 |
| **Workflow Designer** | YAML workflow builder integrated into control panel | High | ✅ Available | v1.1.6 |
| **Data Source Configuration** | UI for configuring and managing data source connections | High | ✅ Available | v1.1.6 |
| **LLM Provider Management** | Configure and manage LLM provider credentials and settings | High | ✅ Available | v1.1.6 |
| **Chatbot Management** | Create and configure chatbots | High | ✅ Available | v1.1.6 |
| **Voice Agent Management** | Configure voice agents, telephony, speech-to-text and text-to-speech providers, and call tools | High | ✅ Available | v1.1.6 |
| **Knowledge Base Management** | Create knowledge bases and manage their documents | Medium | ✅ Available | v1.1.6 |
| **Trigger & Schedule Management** | Configure triggers and scheduled jobs | Medium | ✅ Available | v1.1.6 |
| **RBAC Configuration** | Visual interface for managing roles and permissions | High | Yet to start | TBD |
| **Guardrail Configuration** | Configure AI guardrails and safety policies | High | 🔄 In Progress | v1.1.14 |
| **User Management** | Manage users and their access to applications. Group management is not yet available | High | 🔄 In Progress | TBD |
| **Dashboard & Analytics** | Overview dashboard with key metrics and analytics | Medium | Yet to start | TBD |
| **Agent Testing Interface** | Built-in interface for testing agents before deployment | Medium | Yet to start | TBD |
| **Workflow Monitoring** | Real-time monitoring of workflow executions. Run history and async execution status are available | High | 🔄 In Progress | TBD |

### Advanced Features

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **No-Code Agent Builder** | Visual, no-code interface for building agents | High | Yet to start | v2.0.0|
| **Template Marketplace** | Browse and use pre-built agent and workflow templates | Medium | Yet to start | v2.0.0|
| **Version Control UI** | Visual interface for agent and workflow versioning and rollback | Medium | ✅ Available | v1.1.6 |
| **Cost Analytics Dashboard** | Detailed cost tracking and analytics per agent/workflow (OTLP) | High | ✅ Available | v1.1.6 |
| **Performance Analytics** | Performance metrics and optimization recommendations | Medium | Yet to start | v2.0.0|
| **Collaboration Features** | Share agents/workflows, comments, and team collaboration | Low | Yet to start | v2.0.0|

---

## 💻 Wavefront CLI

Command-line interface for configuring and managing Wavefront AI.

### Core Features

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Agent Management** | Create, update, delete, and list agents via CLI | High | Yet to start | TBD |
| **Workflow Management** | Manage workflows from command line | High | Yet to start | TBD |
| **Data Source Configuration** | Configure data sources via CLI | High | Yet to start | TBD |
| **Authentication** | CLI authentication and session management | High | Yet to start | TBD |
| **YAML Import/Export** | Import and export agent/workflow configurations | High | Yet to start | TBD |
| **Local Development** | Local development server and testing tools | Medium | Yet to start | TBD |
| **Deployment** | Deploy agents and workflows to Wavefront Cloud | Medium | Yet to start | TBD |
| **Configuration Management** | Manage multiple environments (dev, staging, prod) | Medium | Yet to start | TBD |
| **Bulk Operations** | Bulk import/export, update, and delete operations | Low | Yet to start | TBD |

---

## 🔌 Data & Integration Layer

### Data Adapters

| Adapter | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **BigQuery** | Full read/write support for Google BigQuery | High | ✅ Available | v1.1.6 |
| **Amazon Redshift** | Production-ready Redshift integration | High | ✅ Available | v1.1.6 |
| **PostgreSQL** | Optimized PostgreSQL adapter for large datasets | High | ✅ Available | v1.1.6 |
| **SQL Server** | Microsoft SQL Server adapter | Medium | ✅ Available | v1.1.6 |
| **Dynamic Queries** | Parameterised, YAML-defined queries per datasource, with execution and CSV export | High | ✅ Available | v1.1.6 |
| **MySQL** | MySQL 5.7+ compatible adapter | Medium | Yet to start | TBD |
| **MongoDB** | NoSQL database adapter for MongoDB | Medium | Yet to start | TBD |
| **Snowflake** | Snowflake data warehouse integration | High | Yet to start | TBD |
| **Databricks** | Databricks Lakehouse integration | Medium | Yet to start | TBD |
| **Elasticsearch** | Elasticsearch integration for search and analytics | Medium | Yet to start | TBD |
| **Redis** | Redis adapter for caching and real-time data | Low | Yet to start | TBD |

### Cloud Storage

| Adapter | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **AWS S3** | S3 integration for file storage and retrieval | High | ✅ Available (beta) | v1.1.6 |
| **Google Cloud Storage** | GCS integration for file operations | High | ✅ Available (beta) | v1.1.6 |
| **Azure Blob Storage** | Azure Blob Storage integration | Medium | ✅ Available (beta) | v1.1.6 |
| **HDFS** | Hadoop Distributed File System support | Low | Yet to start | TBD |

### API Adapters

| Adapter | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Custom API Configuration** | Flexible HTTP endpoint support with custom authentication | High | ✅ Available | v1.1.6 |
| **Gmail** | Gmail connection for email tools and triggers | Medium | ✅ Available | v1.1.6 |
| **Salesforce** | Native Salesforce API integration (reachable today through Custom API Configuration) | High | Yet to start | TBD |
| **SAP** | SAP ERP system integration | Medium | Yet to start | TBD |
| **Jira** | Jira API integration for project management | Low | Yet to start | v2.0.0|
| **Slack** | Native Slack integration for notifications and workflows (reachable today through Custom API Configuration) | Medium | Yet to start | TBD |
| **Microsoft 365** | Microsoft 365 API integration | Medium | Yet to start | TBD |
| **GitHub/GitLab** | Version control system integrations | Low | Yet to start | v2.0.0|

### LLM Connectors

| Model/Service | Description | Priority | Status | Target Release |
|---------------|-------------|----------|--------|----------------|
| **OpenAI** | OpenAI GPT models | High | ✅ Available | v1.0.0 |
| **Anthropic** | Claude models | High | ✅ Available | v1.0.0 |
| **vLLM (Open-Source)** | Self-hosted inference with vLLM | High | ✅ Available | v1.0.0 |
| **Ollama** | Local model deployment with Ollama | High | ✅ Available | v1.0.0 |
| **Google Vertex AI** | Google Cloud Vertex AI integration | High | ✅ Available | v1.0.0 |
| **Google Gemini** | Direct Gemini API integration | High | ✅ Available | v1.0.0 |
| **GroqAI** | Fast inference support with Groq | Medium | ✅ Available | v1.1.0 |
| **AWS Bedrock** | AWS Bedrock integration (available in flo-ai) | High | ✅ Available | v1.1.0 |
| **Azure OpenAI** | Azure OpenAI Service integration | Medium | ✅ Available | v1.1.0 |

---

## 🎨 Developer Experience

### Developer Tools

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **JavaScript/TypeScript SDK** | Frontend SDK for React and other frameworks | High | Yet to start | TBD |
| **API Documentation** | Interactive API documentation (Swagger/OpenAPI) | High | Yet to start | TBD |
| **SDK Examples** | Comprehensive examples for all SDKs | Medium | Yet to start | TBD |

---

## 🏢 Enterprise Features

### AI Guardrails & Safety

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Content Moderation** | Automatic content filtering and moderation | High | 🔄 In Progress | v1.1.14 |
| **Toxicity Detection** | Detect and prevent toxic or harmful outputs | High | 🔄 In Progress | v1.1.14 |
| **PII Detection** | Detect and redact personally identifiable information | High | 🔄 In Progress | v1.1.14 |
| **Custom Guardrails** | Define custom guardrail rules and policies | High | 🔄 In Progress | v1.1.14 |
| **Guardrail Monitoring** | Monitor guardrail violations and alerts | Medium | 🔄 In Progress | v1.1.14 |
| **Compliance Reporting** | Generate compliance reports for audits | Medium | Yet to start | TBD|

### Knowledge Bases & RAG

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **MCP Connectors** | Model Context Protocol connectors | High | Yet to start | TBD |
| **Vector Database Integration** | PostgreSQL with pgvector | High | ✅ Available | v1.1.6 |
| **Document Ingestion** | Automated document ingestion and processing on background workers | High | ✅ Available| v1.1.6 |
| **RAG Pipeline** | Hybrid vector and keyword retrieval with reranking | High | ✅ Available | v1.1.6 |
| **Image Search** | Retrieval over images | Medium | ✅ Available | v1.1.6 |
| **Knowledge Base Management** | UI for managing knowledge bases | Medium | ✅ Available | v2.0.0|

### Voice & Conversational AI

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Voice-to-Voice Bots** | Voice-enabled conversational agents built on Pipecat | Medium | ✅ Available | v1.1.6 |
| **Inbound & Outbound Calls** | Receive calls on configured numbers and place outbound calls | High | ✅ Available | v1.1.6 |
| **Telephony Providers** | Twilio, Exotel and Smartflo | High | ✅ Available | v1.1.6 |
| **ASR Integration** | Speech-to-text with Deepgram, AssemblyAI, Whisper, Google, Azure, Sarvam and ElevenLabs | Medium | ✅ Available | v1.1.6 |
| **TTS Integration** | Text-to-speech with ElevenLabs, Deepgram, Cartesia, Azure, Google, AWS and Sarvam | Medium | ✅ Available | v1.1.6 |
| **Multi-language Calls** | Multiple languages per voice agent, with language detection | Medium | ✅ Available | v1.1.6 |
| **Tools During Calls** | API and Python tools that voice agents can call mid-conversation | Medium | ✅ Available | v1.1.6 |
| **Post-call Evaluation** | LLM-based evaluation of each call, recorded in telemetry | Medium | ✅ Available | v1.1.6 |
| **Contact Center Integration** | Integration with contact center platforms | Low | ✅ Available | v1.1.6 |

---

## 📊 Observability & Monitoring

### Telemetry & Metrics

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **OpenTelemetry Integration** | Full OpenTelemetry support | High | ✅ Available | v1.1.9 |
| **Pluggable Cloud APM Export** | Push traces/metrics to Azure App Insights, AWS X-Ray/CloudWatch, GCP Cloud Trace, or any OTLP vendor | High | ✅ Available | v1.1.9 |
| **Grafana Dashboards** | Pre-built Grafana dashboards | High | Yet to start | v1.1.9 |
| **Application Metrics** | Application-level performance metrics | High | ✅ Available | v1.1.9 |
| **AI Token Tracking** | Token usage tracking per agent | High | ✅ Available | v1.1.9 |

### Logging & Audit

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Structured Logging** | Structured logging with JSON output | High | ✅ Available | v1.0.0 |
| **AI Audit Logging** | Detailed decision trails for AI agents | High | Yet to start | TBD |
| **Access Audit Logs** | Comprehensive access and permission audit logs. Datasource operations are already audit logged | High | 🔄 In Progress | TBD |

---

## 📝 Notes

- **Version Numbers**: Version numbers are estimates and subject to change based on priorities and community feedback.

- **Community Contributions**: The community is welcome to suggest changes to the roadmap through pull requests. Community-suggested features will be evaluated and prioritized based on alignment with project goals.

- **Timeline Estimates**: All timelines are estimates and may change based on rootflo priorities, community feedback, and resource availability.

---

## 🤝 Contributing to the Roadmap

We welcome community input on the roadmap! Here's how you can contribute:

1. **Suggest New Features**: Open an issue or pull request to suggest new features
2. **Prioritize Features**: Comment on existing roadmap items to indicate what's most important to you
3. **Contribute Code**: Pick up any "Yet to start" item and submit a PR
4. **Provide Feedback**: Share your thoughts on the roadmap direction

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed contribution guidelines.

---

**Last Updated**: September 2026
