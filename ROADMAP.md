# Wavefront AI Roadmap

This roadmap provides a comprehensive overview of the direction Wavefront AI is heading. It covers all major components of the platform: the Flo AI library, Wavefront Core middleware, Control Panel, CLI, and ecosystem tools.

The roadmap is organized by component and priority. We welcome community feedback and contributions!

## 🗓️ Release Timeline

| Quarter | Milestone | Key Deliverables |
|---------|-----------|------------------|
| **Nov 2025** | Public README.md | Publish readme and gather community feedback |
| **Dec 2025** | Community Edition MVP | Open-source community edition with working MVP |
| **Q1 2026** | Enterprise Edition | Advanced RBAC, additional data source integrations |
| **Q1 2026** | Wavefront Cloud | One-click deployable Wavefront Cloud |

---

## 📊 Beta Release Scope

Current release has the following features implemented:

| Feature | Limitation | 
|---------|------------|
| **Datasource** | You can connect to multiple data sources. Current support is for Google Bigquery and AWS redshift. |
| **Agent** | You can create agents using the console and run them using the middleware. |
| **Workflow** | You can create workflows using the console and run them using the middleware. |
| **Voice Bots** | You can process voice calls using the middleware. But currently only outgoing calls are supported. Only supported telephony service is Twilio |
| **Inference App** | You can create inference pytorch models using the middleware, but the support is limited to certain pytorch models. This feature is fully `experimental`, and APIs are bound to change. |
| **API Service** | You can create API services to connect to any backend service. We have provided support for JSON and non JSON payload. Authenticate is limited to API Key, Basic Auth & Bearer Token. |

## 🤖 Flo AI Library

The core agent building and orchestration framework. The following are that is going to be implemented in the coming releases

### Core Features

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Resume Work** | Functionality that lets agents resume from where they stopped, with state persistence | High | Yet to start | v1.1.0 |
| **Code to YAML** | Convert code-built agents into YAML format for version control and sharing | Medium | Yet to start | v1.2.0 |
| **Model Router** | Intelligent model routing within agents, allowing dynamic LLM selection based on task complexity | High | Yet to start | v1.2.0 |
| **Parallel Router** | Execute independent tasks or agents in parallel for improved performance | High | Yet to start | TBD |
| **Agent Versioning** | Version control for agent configurations and workflows | Medium | Yet to start | TBD |
| **Agent Templates** | Pre-built agent templates for common use cases (customer support, data analysis, etc.) | Medium | Yet to start | TBD |
| **Streaming Responses** | Real-time streaming of agent responses for better UX | High | Yet to start | In-Progress |
| **Multi-modal Support** | Support for image, audio, and video inputs/outputs | Medium | Yet to start | In-Progress |
| **Custom Memory Backends** | Support for Redis, PostgreSQL, and other backends for agent memory | Medium | Yet to start | TBD |

### Observability & Debugging

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Recursion Control** | Expose parameters to limit recursions and define policies for recursion handling | High | Yet to start | v1.2.0 |
| **Token Count Tracking** | Expose total tokens used by agent execution directly through session | High | ✅ Available | v0.1.0 |
| **Execution Time Metrics** | Detailed timing metrics for each agent and tool execution | Medium | ✅ Available | v0.1.0 |
| **Debug Mode** | Enhanced debugging mode with step-by-step execution logs | Medium | Yet to start | TBD |
| **Performance Profiling** | Identify bottlenecks in agent workflows | Medium | Yet to start | TBD |

### Advanced Orchestration

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Conditional Workflows** | Advanced conditional logic in YAML workflows | Medium | ✅ Available | v0.1.0 |
| **Loop & Iteration** | Support for loops and iterations in workflows | Medium | ✅ Available | v0.1.0 |
| **Error Recovery Strategies** | Configurable error recovery strategies per agent | High | ✅ Available | v0.1.0 |
| **Workflow Scheduling** | Schedule workflows to run at specific times or intervals | Low | ✅ Available | TBD |

---

## 🏗️ Wavefront Core Middleware (a.k.a Floware)

The core middleware service that provides APIs, authentication, authorization, and data connectivity.

### Core Services

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **REST API** | Comprehensive REST API for agent management, workflow execution, and data access | High | ✅ Available | v0.1.0 |
| **WebSocket Support** | Real-time communication for streaming agent responses | High | ✅ Available | v0.1.0 |
| **Agent Registry** | Centralized registry for storing and managing agent definitions | High | ✅ Available | v0.1.0 |
| **Workflow Engine** | Server-side workflow execution engine | High | ✅ Available | v0.1.0 |
| **API Gateway** | Unified API gateway with rate limiting and request routing | Medium | ✅ Available | v0.1.0 |

### Authentication & Authorization

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Google Auth Integration** | OAuth 2.0 integration with Google | High | ✅ Available | v0.1.0 |
| **Microsoft AD/Entra** | Enterprise SSO with Microsoft Active Directory | High | ✅ Available | v0.1.0 |
| **Okta Integration** | SSO integration with Okta | High | Yet to start | v0.2.0 |
| **SAML 2.0 Support** | Standard SAML 2.0 authentication | High | Yet to start | v0.2.0 |
| **LDAP Integration** | LDAP/Active Directory integration | Medium | Yet to start | v0.2.0 |
| **Auth0 Integration** | Auth0 SSO support | Medium | Yet to start | v0.2.0 |
| **Multi-Factor Authentication** | MFA support for enhanced security | Medium | Yet to start | v0.3.0 |
| **API Key Management** | Secure API key generation and rotation | High | ✅ Available | v0.1.0 |
| **OAuth 2.0 Client Credentials** | OAuth 2.0 client credentials flow for service-to-service auth | Medium | Yet to start | v0.2.0 |

### RBAC & Permissions

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Agent-Level RBAC** | Fine-grained permissions for agent access and execution | High | Yet to start | v0.1.0 |
| **Data Source RBAC** | Granular permissions for data source access | High | Yet to start | v0.1.0 |
| **Role Management** | Create, update, and manage custom roles | High | ✅ Available | v0.1.0 |
| **Audit Logging for Access** | Comprehensive audit logs for all access attempts | High | Yet to start | v0.1.0 |

---

## 🎛️ Wavefront Control Panel (a.k.a Flo Console)

Unified frontend for configuring agents, workflows, AI models, guardrails, and RBAC.

### Core Features

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Agent Management UI** | YAML interface for creating, editing, and managing agents | High | ✅ Available | v0.1.0 |
| **Workflow Designer** | YAML workflow builder integrated into control panel | High | ✅ Available | v0.1.0 |
| **Data Source Configuration** | UI for configuring and managing data source connections | High | ✅ Available | v0.1.0 |
| **LLM Provider Management** | Configure and manage LLM provider credentials and settings | High | ✅ Available | v0.1.0 |
| **RBAC Configuration** | Visual interface for managing roles and permissions | High | Yet to start | v0.2.0 |
| **Guardrail Configuration** | Configure AI guardrails and safety policies | High | Yet to start | v0.2.0 |
| **User Management** | Manage users, groups, and their access | High | Yet to start | v0.2.0 |
| **Dashboard & Analytics** | Overview dashboard with key metrics and analytics | Medium | Yet to start | TBD |
| **Agent Testing Interface** | Built-in interface for testing agents before deployment | Medium | Yet to start | TBD |
| **Workflow Monitoring** | Real-time monitoring of workflow executions | High | Yet to start | v0.1.0 |

### Advanced Features

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **No-Code Agent Builder** | Visual, no-code interface for building agents | High | Yet to start | v0.3.0 |
| **Template Marketplace** | Browse and use pre-built agent and workflow templates | Medium | Yet to start | v0.3.0 |
| **Version Control UI** | Visual interface for agent versioning and rollback | Medium | Yet to start | v0.2.0 |
| **Cost Analytics Dashboard** | Detailed cost tracking and analytics per agent/workflow | High | Yet to start | v0.2.0 |
| **Performance Analytics** | Performance metrics and optimization recommendations | Medium | Yet to start | v0.3.0 |
| **Collaboration Features** | Share agents/workflows, comments, and team collaboration | Low | Yet to start | v0.3.0 |

---

## 💻 Wavefront CLI

Command-line interface for configuring and managing Wavefront AI.

### Core Features

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Agent Management** | Create, update, delete, and list agents via CLI | High | Yet to start | v0.4.0 |
| **Workflow Management** | Manage workflows from command line | High | Yet to start | v0.4.0 |
| **Data Source Configuration** | Configure data sources via CLI | High | Yet to start | v0.4.0 |
| **Authentication** | CLI authentication and session management | High | Yet to start | v0.4.0 |
| **YAML Import/Export** | Import and export agent/workflow configurations | High | Yet to start | v0.4.0 |
| **Local Development** | Local development server and testing tools | Medium | Yet to start | v0.4.0 |
| **Deployment** | Deploy agents and workflows to Wavefront Cloud | Medium | Yet to start | v0.4.0 |
| **Configuration Management** | Manage multiple environments (dev, staging, prod) | Medium | Yet to start | v0.4.0 |
| **Bulk Operations** | Bulk import/export, update, and delete operations | Low | Yet to start | v0.4.0 |

---

## 🔌 Data & Integration Layer

### Data Adapters

| Adapter | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **BigQuery** | Full read/write support for Google BigQuery | High | ✅ Available | v0.1.0 |
| **Amazon Redshift** | Production-ready Redshift integration | High | ✅ Available | v0.1.0 |
| **PostgreSQL** | Optimized PostgreSQL adapter for large datasets | High | 🔄 In Progress | v0.1.0 |
| **MySQL** | MySQL 5.7+ compatible adapter | Medium | Yet to start | TBD |
| **MongoDB** | NoSQL database adapter for MongoDB | Medium | Yet to start | TBD |
| **SQL Server** | Microsoft SQL Server adapter | Medium | Yet to start | TBD |
| **Snowflake** | Snowflake data warehouse integration | High | Yet to start | TBD |
| **Databricks** | Databricks Lakehouse integration | Medium | Yet to start | TBD |
| **Elasticsearch** | Elasticsearch integration for search and analytics | Medium | Yet to start | TBD |
| **Redis** | Redis adapter for caching and real-time data | Low | Yet to start | TBD |

### Cloud Storage

| Adapter | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **AWS S3** | S3 integration for file storage and retrieval | High | Yet to start | v0.2.0 |
| **Google Cloud Storage** | GCS integration for file operations | High | Yet to start | v0.2.0 |
| **Azure Blob Storage** | Azure Blob Storage integration | Medium | Yet to start | v0.2.0 |
| **HDFS** | Hadoop Distributed File System support | Low | Yet to start | v0.3.0 |

### API Adapters

| Adapter | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Custom API Configuration** | Flexible HTTP endpoint support with custom authentication | High | ✅ Available | v0.1.0 |
| **Salesforce** | Native Salesforce API integration | High | 🔄 In Progress | v0.1.0 |
| **SAP** | SAP ERP system integration | Medium | Yet to start | v0.2.0 |
| **Jira** | Jira API integration for project management | Low | Yet to start | v0.3.0 |
| **Slack** | Slack API integration for notifications and workflows | Medium | ✅ Available | v0.2.0 |
| **Microsoft 365** | Microsoft 365 API integration | Medium | Yet to start | v0.2.0 |
| **GitHub/GitLab** | Version control system integrations | Low | Yet to start | v0.3.0 |

### LLM Connectors

| Model/Service | Description | Priority | Status | Target Release |
|---------------|-------------|----------|--------|----------------|
| **OpenAI** | GPT-3.5, GPT-4, GPT-4 Turbo support | High | ✅ Available | v1.0.0 |
| **Anthropic** | Claude models (Sonnet, Opus, Haiku) | High | ✅ Available | v1.0.0 |
| **vLLM (Open-Source)** | Self-hosted inference with vLLM | High | ✅ Available | v1.0.0 |
| **Ollama** | Local model deployment with Ollama | High | ✅ Available | v1.0.0 |
| **Google Vertex AI** | Google Cloud Vertex AI integration | High | ✅ Available | v1.0.0 |
| **Google Gemini** | Direct Gemini API integration | High | ✅ Available | v1.0.0 |
| **GroqAI** | Fast inference support with Groq | Medium | 🔄 In Progress | v1.1.0 |
| **AWS Bedrock** | AWS Bedrock integration | High | 🔄 In Progress | v1.1.0 |
| **Azure OpenAI** | Azure OpenAI Service integration | Medium | Yet to start | v1.2.0 |
| **Cohere** | Cohere model integration | Medium | Yet to start | v1.2.0 |
| **Mistral AI** | Mistral AI model support | Medium | Yet to start | v1.2.0 |
| **Together AI** | Together AI inference platform | Low | Yet to start | v1.3.0 |
| **Custom Model Endpoints** | Support for custom model endpoints | Medium | Yet to start | v1.2.0 |

---

## 🎨 Developer Experience

### Developer Tools

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **JavaScript/TypeScript SDK** | Frontend SDK for React and other frameworks | High | ✅ Available | v1.0.0 |
| **API Documentation** | Interactive API documentation (Swagger/OpenAPI) | High | Yet to start | v0.1.0 |
| **SDK Examples** | Comprehensive examples for all SDKs | Medium | Yet to start | v1.1.0 |

---

## 🏢 Enterprise Features

### AI Guardrails & Safety

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Content Moderation** | Automatic content filtering and moderation | High | Yet to start | v0.2.0 |
| **Toxicity Detection** | Detect and prevent toxic or harmful outputs | High | Yet to start | v0.2.0 |
| **PII Detection** | Detect and redact personally identifiable information | High | Yet to start | v0.2.0 |
| **Custom Guardrails** | Define custom guardrail rules and policies | High | Yet to start | v0.2.0 |
| **Guardrail Monitoring** | Monitor guardrail violations and alerts | Medium | Yet to start | v0.3.0 |
| **Compliance Reporting** | Generate compliance reports for audits | Medium | Yet to start | v0.3.0 |

### Knowledge Bases & RAG

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **MCP Connectors** | Model Context Protocol connectors | High | Yet to start | v0.1.0 |
| **Vector Database Integration** | Support for PostgresSQL, etc. | High | ✅ Available | v0.2.0 |
| **Document Ingestion** | Automated document ingestion and processing | High | ✅ Available| v0.2.0 |
| **RAG Pipeline** | Built-in RAG pipeline configuration | High | ✅ Available | v0.2.0 |
| **Knowledge Base Management** | UI for managing knowledge bases | Medium | ✅ Available | v0.3.0 |

### Voice & Conversational AI

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Voice-to-Voice Bots** | Voice-enabled conversational agents | Medium | ✅ Available | v0.1.0 |
| **ASR Integration** | Automatic Speech Recognition integration | Medium | ✅ Available | v0.1.0 |
| **TTS Integration** | Text-to-Speech integration | Medium | ✅ Available | v0.1.0 |
| **Contact Center Integration** | Integration with contact center platforms | Low | ✅ Available | v0.1.0 |

---

## 📊 Observability & Monitoring

### Telemetry & Metrics

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **OpenTelemetry Integration** | Full OpenTelemetry support | High | ✅ Available | v1.0.0 |
| **Prometheus Metrics** | Prometheus-compatible metrics | High | ✅ Available | v1.0.0 |
| **Grafana Dashboards** | Pre-built Grafana dashboards | High | Yet to start | v0.1.0 |
| **Application Metrics** | Application-level performance metrics | High | ✅ Available | v1.0.0 |
| **AI Token Tracking** | Token usage tracking per agent | High | ✅ Available | v1.0.0 |

### Logging & Audit

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Structured Logging** | Structured logging with JSON output | High | ✅ Available | v1.0.0 |
| **AI Audit Logging** | Detailed decision trails for AI agents | High | 🔄 In Progress | v0.1.0 |
| **Access Audit Logs** | Comprehensive access and permission audit logs | High | Yet to start | v0.1.0 |

### Monitoring & Alerts

| Feature | Description | Priority | Status | Target Release |
|---------|-------------|----------|--------|----------------|
| **Real-time Monitoring** | Real-time monitoring of agent executions | High | Yet to start | v0.1.0 |
| **Alert System** | Configurable alerts for errors, performance, and costs | High | Yet to start | v0.2.0 |
| **Health Checks** | Health check endpoints for all services | High | Yet to start | v0.1.0 |
| **Performance Monitoring** | Detailed performance monitoring and profiling | Medium | Yet to start | v0.2.0 |
| **SLA Monitoring** | Service level agreement monitoring | Low | Yet to start | v0.3.0 |

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

**Last Updated**: November 2025  
**Next Review**: December 2025
