Goal
Build a configurable, enterprise-grade API proxy middleware that acts as an intelligent gateway between clients and multiple backend services. The middleware handles routing, authentication injection, and request/response transformation—all driven by declarative YAML configuration, eliminating the need for code changes when adding new backends or services.
Problem Statement
Organizations often need to:
Expose internal/external APIs through a unified interface
Manage authentication for multiple heterogeneous backend services (OAuth2, API keys, Basic Auth, etc.)
Avoid duplicating auth logic across client applications
Centralize request routing and transformation logic
Support multiple authentication schemes without code changes
Current solutions require either custom code for each backend or complex infrastructure. We need a simple, configuration-driven middleware.
Core Features
1. Proxy Layer
Forward HTTP requests (GET, POST, PUT, DELETE, PATCH) to configured backends
Preserve client headers and query parameters
Support request body forwarding
Return backend response as-is or transformed
2. Routing & Service Registry
Route incoming /api/{service_name} requests to correct backend
Support dynamic service-to-backend mapping via YAML
Handle multiple backends with different base URLs
Support service aliasing and versioning (future)
3. Authentication Layer
Bearer Token: Static token injection
Basic Auth: Username/password encoding
API Key: Custom header injection
OAuth2: Client credentials flow with auto-refresh and caching
HMAC: Signature generation for request validation
AWS SigV4: AWS request signing (future)
Automatic header merging with client headers
4. Token Management
In-memory token cache with expiration tracking
Automatic OAuth2 token refresh before expiry
Graceful fallback on auth failures
Architecture
High-Level Components

Client Request
    ↓
FastAPI Router
    ↓
Service Registry (YAML configs)
    ↓
Auth Manager (AuthManager class)
    ├─ Bearer Handler
    ├─ Basic Auth Handler
    ├─ API Key Handler
    ├─ OAuth2 Handler
    ├─ HMAC Handler
    └─ [Pluggable handlers]
    ↓
HTTP Client (httpx with retry/timeout)
    ↓
Backend Service
    ↓
Response (return to client)

Key Components
service-config.yaml – Backend and service definitions
AuthManager – Central auth orchestration
Auth Handlers – Pluggable auth type implementations
Proxy Router – FastAPI route handler

Implementation
Phase 1 (MVP - 2 weeks, ~10 days effort)
Service Definition Standard(Auth Layer & Services/APIs)

Define Yaml based service definition( named as <name>-service-definition.yaml ). One middleware app can have multiple services configured, meaning multiple service definitions available. Each service definition is grouped into logical groups called services.
egs: crm-service-definition.yaml, gupsupp-service-defintion.yaml etc

Services -> (Auth + CRM Services)
            (Auth + Marketing services)
            (Auth + CPaaS Services)

Each service defintion will have the following configurations:
Authentication Configurations: To to authenticate and authorizer to the backend service
Service/API configurations: The APIs that are exposed to the client from backend

Service Schema:
service:
  # ID has to be unique and should not contain spaces
  id: <service_id>
  # (base url of the servvice)
  base_url: string

  auth:
    <Auth Configurations>
  apis:
    <API Configurations>

Authentication Configurations
We only plan to support 3 types of autheticators (Bearer, Basic, API Key) in Phase 1. The authentication configuration will have the following things:

The auth configuration based on the type of auth choosen by the user
Additional headers to be added if any.
Pre execution script which can get executed, just before sending the request (pre-processor)

Auth Schema:
auth:
    # id of the authenticator (eg: facebook-auth-service)
    id: string
    # can be v1 or v2, defaulting to v1 if not provided
    version: string
    type: string (bearer | basic | api_key)
    #(Optional if the auth service is hosted seperately)
    base_url: string | null
    path: string (path to the auth API)

    # Auth type-specific configuration
    # (see examples below)

    # Additional static headers to inject (optional)
    additional_headers:
      {header_name}: string
      {header_name}: string
      # Examples: X-Custom-Header, X-Request-ID, etc.

    # Pre-execution script (preprocessor)
    preprocessor:
      enabled: boolean (default: false)
      script_path: string (path to script)

Examples:


The auth excution hierarachy:
(Request Start)
  -> Authenticator (based on type)
      -> Add additional headers (if any)
          -> Auth Pre-Processor
              -> (Request is Handed over to APIs Implementation)
Note: Generally authenticators are part of the overall APIs, and they are called as part of the API call. But if the client wants to directly utilize the auth API, they should be able to call /services/<service_id>/authenticators/<auth_version>/<authenticator_id>
Post-Processor Schema

For the authenticator the post processor function with look something like this, in terms of definition:
const main = (auth_config, request_context) => {
  """
    Preprocessor function that modifies auth config before request.

    Args:
        auth_config: Current auth configuration dict (type, token, or other                       authenticator specific values
        request_context: Request metadata (method, path, etc.)

    Returns:
        dict: {
            \"auth_config\": modified auth_config,
            \"additional_headers\": dict of headers to add
        }
   """
}

Please find example auth preprocessors inside
API/Service Configurations
This part defines the APIs and how to call them. The API configurations will have the following parts:

The URL path of the API to call (the base_url comes from service level base_url)
The ID of the API
Any additional headers
Output mapper: This helps transform the payload of the backend API, if required
Pre-processor script: The script to modify request before sending to backend
Post-processor script: The script for modifying payload or response to client.

API Schema:
apis:
  - id: string (id of the API)
    version: string (optional with default to v1)
    path: string (e.g., /users, /transactions/{id})
    method: string (GET | POST | PUT | DELETE | PATCH)

    # Optional: Additional headers specific to this API
    additional_headers:
      {header_name}: string
      {header_name}: string

    # Optional: Preprocess/modify request before sending to backend
    preprocessor:
      enabled: boolean (default: false)
      script_path: string (path to Python script)
      # Modifies request body, path parameters, headers

    # Optional: Transform backend response payload
    output_mapper:
      enabled: boolean (default: false)
      mapper:
        <backend_key1>: <mapped_key1>
        <backend_key2.inner_key1>: <mapped_key2.inner_key1>
        <backend_key2.inner_key2>: <mapped_key3>
        # Maps response fields from backend to client format

    # Optional: Postprocess/modify response before sending to client
    postprocessor:
      enabled: boolean (default: false)
      script_path: string (path to Python script)
      # Modifies response body, headers, status code

Examples:


The auth excution hierarachy:
(Request Start)
  -> Authenticator (based on type)
      -> Add additional headers (if any)
          -> Auth Pre-Processor
            ............ auth layer ends & api layer starts .........
              -> API preprocessor
                  -> Add additional API headers
                    -> Request Preprocessor
                      -> Response Sent to Backend
                        -> Response Output Mapper
                           -> Response Post processor
                              -> Response sent to client
Here is the of full Service Definition Schema
service:
  # ID has to be unique and should not contain spaces
  id: <service_id>
  # (base url of the servvice)
  base_url: string

  auth:
    # id of the authenticator (eg: facebook-auth-service)
    id: string
    # can be v1 or v2, defaulting to v1 if not provided
    version: string
    type: string (bearer | basic | api_key)
    #(Optional if the auth service is hosted seperately)
    base_url: string | null
    path: string (path to the auth API)

    # Auth type-specific configuration
    # (see examples below)

    # Additional static headers to inject (optional)
    additional_headers:
      {header_name}: string
      {header_name}: string
      # Examples: X-Custom-Header, X-Request-ID, etc.

    # Pre-execution script (preprocessor)
    preprocessor:
      enabled: boolean (default: false)
      script_path: string (path to script)
  apis:
    - id: string (id of the API)
      version: string (optional with default to v1)
      path: string (e.g., /users, /transactions/{id})
      method: string (GET | POST | PUT | DELETE | PATCH)

      # Optional: Additional headers specific to this API
      additional_headers:
        {header_name}: string
        {header_name}: string

      # Optional: Preprocess/modify request before sending to backend
      preprocessor:
        enabled: boolean (default: false)
        script_path: string (path to Python script)
        # Modifies request body, path parameters, headers

      # Optional: Transform backend response payload
      output_mapper:
        enabled: boolean (default: false)
        mapper:
          <backend_key1>: <mapped_key1>
          <backend_key2.inner_key1>: <mapped_key2.inner_key1>
          <backend_key2.inner_key2>: <mapped_key3>
          # Maps response fields from backend to client format

      # Optional: Postprocess/modify response before sending to client
      postprocessor:
        enabled: boolean (default: false)
        script_path: string (path to Python script)
        # Modifies response body, headers, status code
API from Client
The API call from client to the backend API will be:
POST /floware/v1/services/<service_id>/apis/<api_version>/<api_id>?<query_params>
All request will be POST, as other verbs are configured at backend.
Response Schema:
{
    "meta": {
       "status": <Rootflo Internal Status Codes>,
        "message": <Rootflo Internal Status Messages>,
        "trace": <Execution Trace> (Refer Task Breakdown Task No: 9)
    }
    "data" <Response to client>
}
Service Layer Implementation.

The implementation of the Service Layer involves following components:
Service registry: Where the service definitions are maintained, basically CRUD for all the yaml definitions
Service Definition Parser: A parser class to parser and convert service definitions to POJO classes
Core proxy pipeline: The main middleware router/proxy which does the execution. This have multiple subcomponents
Auth Manager: Manages different kinds of auth
Service Manager: Manages different kinds of api calls
Error handling & logging: Handling error and forwarding the same to client
Unit Testing: Unit test the code functionalities thoroughly

Most of the stuff is straight forward, except for Core Proxy Pipeline, which is the code component. Let's elaborate on this.

Core proxy pipeline

Implementation wise and design pattern wise, what we have at hand is a pipeline, The pipeline gets triggered when an API call is hit. We can call it a pipeline because multiple things happen in sequence (at least from the facade layer it looks like sequence, even though we can optimise later). So every service definition has to become a pipeline, which is then runtime cached to process the API requests

Auth pipeline
[Authenticator → Header Injector → Pre-processor ]

API Pipeline
[API processor → Header Injector → Preprocessor → Request to Backend → Mapper →post processor]

Service Pipeline
[Auth pipeline → API Pipeline]

Usage composite pattern to build up. Also all components of the pipeline should be of same type, ie child class of pipeline protocol.

Example Protocol (for reference only):
class PipelineStage(ABC):
    """
    Abstract base class for all pipeline components.

    All pipeline stages (atomic and composite) must implement this protocol.
    This ensures uniform behavior across the entire pipeline architecture.
    """

    @abstractmethod
    def execute(self, context: PipelineContext) -> PipelineContext:
        """
        Execute the pipeline stage.

        Args:
            context: Pipeline context that flows through stages

        Returns:
            Modified context (same object, modified in-place)

        Raises:
            PipelineException: If any stage fails
        """
        pass

    @abstractmethod
    def get_stage_type(self) -> StageType:
        """Get the type of this pipeline stage. stage is the current pipeline node   name"""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get the name/identifier of this pipeline"""
        pass

Phase 1: Task Breakdown

Please reach out to   for any questions
Appendix

Phase 2 (OAuth2 & Extensibility - 2 weeks, ~25 days)

OAuth2 with token caching/refresh
HMAC authentication
Pluggable auth architecture
Retry & timeout strategies
Rate limits
Comprehensive testing
Observability & metrics
