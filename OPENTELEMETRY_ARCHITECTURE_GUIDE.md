# Wavefront OpenTelemetry & APM Architecture: Complete Reference & Deep Dive

This document captures the complete architectural breakdown, codebase changes, concepts, and configuration guide for the **Wavefront OpenTelemetry Observability System**.

---

## 1. Executive Summary & Architecture

Wavefront has transitioned from a legacy, pull-based Prometheus scraping model (`prometheus-client`, custom in-memory counters, and `/v1/_metrics`) to a **push-based OpenTelemetry (OTel) Distributed Tracing & APM Architecture**.

### Core Tenet: Decoupled Multi-Cloud Export
* **Application Services** (`floware`, `celery_worker`, `call_processing`) speak only standard OpenTelemetry Protocol (**OTLP**) to a local **OpenTelemetry Collector Gateway**.
* No vendor-specific cloud SDKs (Azure Monitor, AWS X-Ray, Datadog) are imported into Python application code.
* Switching or adding cloud monitoring vendors is an **infrastructure-only configuration** (selecting a YAML overlay file in the collector) with **zero code changes and zero container rebuilds**.

```
+---------------------------------------------------------------------------------------------------+
|                                       Wavefront Application                                       |
|                                                                                                   |
|  +--------------------------+  +--------------------------+  +---------------------------------+  |
|  | floware (FastAPI)        |  | celery_worker            |  | call_processing (Voice)         |  |
|  | - FastAPI HTTP Spans     |  | - flo_ai Agent Spans     |  | - Pipecat Voice Spans           |  |
|  | - SQLAlchemy DB Spans    |  | - Background LLM Spans   |  | - STT / LLM / TTS Latencies     |  |
|  | - Redis & HTTPX Spans    |  | - Task Duration Metrics  |  | - Session Metadata              |  |
|  | - flo_ai LLM Spans       |  |                          |  |                                 |  |
|  +------------+-------------+  +------------+-------------+  +----------------+----------------+  |
+---------------|-----------------------------|---------------------------------|-------------------+
                | OTLP (gRPC :4317)           | OTLP (gRPC :4317)               | OTLP (gRPC :4317)
                +-----------------------------+---------------------------------+
                                              |
                                              v
                      +-------------------------------------------------+
                      |     OpenTelemetry Collector Contrib Gateway     |
                      |          (otel-collector-contrib)               |
                      |                                                 |
                      |  Receivers:  OTLP gRPC (:4317), HTTP (:4318)    |
                      |  Processors: memory_limiter, batch, resource    |
                      |  Local Pipeline: 100% unsampled -> Jaeger       |
                      |  Cloud Pipeline: PII Redaction -> Tail Sampling |
                      +-----------------------+-------------------------+
                                              |
                     +------------------------+------------------------+
                     | (Local Dev)            | (Cloud APM - Honeycomb | (Azure / AWS / GCP /
                     v                        v  Grafana Cloud, etc.)  v  New Relic / Datadog)
          +--------------------+   +--------------------+   +--------------------+
          |     Jaeger UI      |   |    Honeycomb.io    |   | Azure App Insights |
          |  (Distributed      |   | (Traces, Datasets, |   | AWS X-Ray/CloudW.  |
          |   Traces UI :16686)|   |  BubbleUp, Latency)|   | GCP Cloud Trace    |
          +--------------------+   +--------------------+   +--------------------+
```

---

## 2. The 7 OpenTelemetry Python Packages Explained

| Package | What it is | Why it was added | Where it is used in the codebase |
| :--- | :--- | :--- | :--- |
| **`opentelemetry-api`** | Abstract API contracts for traces, baggage, metrics, and context. | Allows interacting with spans and baggage without coupling code to any engine. | `baggage_middleware.py`, `errors.py`, `baggage_span_processor.py`, `bootstrap.py` |
| **`opentelemetry-sdk`** | Reference implementation of the OTel API (`TracerProvider`, `SpanProcessor`, Batch Queues). | Implements the runtime engine that generates, processes, and prepares spans for export. | `baggage_span_processor.py`, `flo_ai.telemetry` |
| **`opentelemetry-exporter-otlp`** | Protocol exporter transmitting spans/metrics over gRPC (`4317`) or HTTP (`4318`). | Enables pushing telemetry batches across the network to the `otel-collector` container. | `flo_ai.configure_telemetry()` called in `bootstrap.py` |
| **`opentelemetry-instrumentation-fastapi`** | Auto-instrumentor for FastAPI and Starlette apps. | Automatically creates root `SERVER` spans, extracts incoming W3C `traceparent` headers, records route templates, and generates HTTP duration metrics. | `bootstrap.py` (`instrument_fastapi`), called in `floware/server.py` |
| **`opentelemetry-instrumentation-sqlalchemy`** | Auto-instrumentor for SQLAlchemy engines. | Intercepts SQL queries executed on `DatabaseClient`, emitting `db.query` spans containing SQL syntax and query latencies. | `bootstrap.py` (`instrument_sqlalchemy`), called in `floware/server.py` on `db_client.engine` |
| **`opentelemetry-instrumentation-redis`** | Auto-instrumentor for `redis-py` client. | Instruments cache operations (`GET`, `SET`, pipeline commands) into child spans under the active trace. | `bootstrap.py` (`_instrument_clients`) |
| **`opentelemetry-instrumentation-httpx`** | Auto-instrumentor for async/sync `httpx` HTTP clients. | Instruments outbound HTTP calls (external APIs, webhooks, `call_processing`) and injects W3C trace context headers. | `bootstrap.py` (`_instrument_clients`) |

---

## 3. Context Propagation & Baggage Architecture

### W3C Baggage vs Span Attributes
* **Baggage:** Key-value data attached to the execution context that propagates automatically across threads, coroutines, and distributed service boundaries.
* **Problem:** In standard OpenTelemetry, baggage is transport-only and is **not** copied onto spans as searchable attributes.
* **Solution (`BaggageSpanProcessor`):** A custom `SpanProcessor` intercepts `on_start()` for every span in the application and copies `app.*` baggage keys (`app.user.id`, `app.role.id`, `app.session.id`, `app.request.id`) onto all child spans (DB queries, Redis lookups, LLM executions).

### Raw ASGI Middleware vs `BaseHTTPMiddleware`
* Starlette's `BaseHTTPMiddleware` executes downstream handlers in a separate `anyio` task group with a **copied context**, causing `context.attach()` to fail to propagate to route handlers.
* `BaggageMiddleware` is implemented as a **raw ASGI middleware** (`async def __call__(self, scope, receive, send)`), ensuring baggage is attached directly to the active coroutine.

### Middleware Layering Order (Outer $\rightarrow$ Inner)
FastAPI executes middleware in reverse registration order:
1. `FastAPIInstrumentor` *(Outermost — opens the `SERVER` span immediately upon request arrival)*
2. `SecurityHeadersMiddleware` *(Applies CSP and security headers)*
3. `RequireAuthMiddleware` *(Validates JWT / session and attaches `session` to `scope['state']`)*
4. `RequestIdMiddleware` *(Extracts or generates `request_id`)*
5. `BaggageMiddleware` *(Innermost — reads `session` and `request_id`, attaches baggage to context and `SERVER` span)*
6. Route Handlers & Business Logic

### Exception Handling & Span Error Marking
When a FastAPI global exception handler catches an unhandled exception and returns a JSON 500 response without re-raising, the ASGI middleware considers the request successfully handled (`status=OK`). The helper `record_exception_on_span(exc)` in `telemetry/errors.py` explicitly records `exception.type`, `exception.message`, and `exception.stacktrace`, marking the span status as `StatusCode.ERROR`.

---

## 4. OpenTelemetry Collector Architecture & Deep-Merge Overlays

### Additive Overlay Pattern
The OpenTelemetry Collector runs with multiple `--config` flags:
```yaml
command:
  - "--config=/etc/otel/collector-base.yaml"
  - "--config=${OTEL_EXPORTER_OVERLAY:-/etc/otel/exporters/none.yaml}"
```

Because an empty exporter list (`exporters: []`) crashes the collector, `collector-base.yaml` only declares the local pipelines (`traces/local_debug`, `metrics/local_debug`). Cloud overlay files additively introduce the `traces/cloud_upstream` pipeline and specific exporter definitions.

### Available Overlays

| Overlay File | Destination | Required Environment Variables |
| :--- | :--- | :--- |
| [`otel/exporters/none.yaml`](otel/exporters/none.yaml) | Local Jaeger only (Default) | None |
| [`otel/exporters/honeycomb.yaml`](otel/exporters/honeycomb.yaml) | Honeycomb.io | `OTEL_CLOUD_HEADERS_AUTHORIZATION=<api-key>` |
| [`otel/exporters/otlphttp.yaml`](otel/exporters/otlphttp.yaml) | Generic OTLP (Grafana Cloud, Datadog, New Relic, SigNoz) | `OTEL_CLOUD_ENDPOINT`, `OTEL_CLOUD_HEADERS_AUTHORIZATION` |
| [`otel/exporters/azure.yaml`](otel/exporters/azure.yaml) | Azure Application Insights | `APPLICATIONINSIGHTS_CONNECTION_STRING` |
| [`otel/exporters/aws.yaml`](otel/exporters/aws.yaml) | AWS X-Ray (traces) + CloudWatch EMF (metrics) | `AWS_REGION` + IAM Credentials |
| [`otel/exporters/gcp.yaml`](otel/exporters/gcp.yaml) | GCP Cloud Trace + Monitoring | `GOOGLE_CLOUD_PROJECT` + ADC |

---

## 5. Tail Sampling Deep Dive

```yaml
  tail_sampling:
    decision_wait: 10s
    num_traces: 50000
    expected_new_traces_per_sec: 100
    policies:
      - name: errors
        type: status_code
        status_code: { status_codes: [ERROR] }
      - name: slow
        type: latency
        latency: { threshold_ms: 2000 }
      - name: baseline-sample
        type: probabilistic
        probabilistic: { sampling_percentage: 5 }
```

### How it works:
1. **`decision_wait: 10s`**: Buffers spans for 10 seconds so asynchronous database queries, LLM token generations, and Celery tasks finish and arrive at the collector.
2. **`errors` (100% Retention)**: If *any* span in the trace encountered an error, save the entire trace.
3. **`slow` (100% Retention)**: If total trace duration was $\ge 2000\text{ ms}$, save the entire trace.
4. **`baseline-sample` (5% Retention)**: If the request was fast and successful, keep 5% to calculate baseline latency percentiles (p50/p95) while discarding 95% of routine `200 OK` traces, slashing cloud ingestion costs.

### Scaling Past 1 Replica (Production Multi-Pod Topology):
* **Single Pod Gateway**: Handles ~1,000–3,000 spans/sec comfortably (768MB RAM limit).
* **Scaling Beyond 1 Pod**: Because `tail_sampling` requires all spans of a `trace_id` to reach the same collector instance, do not simply increase replica count behind a standard round-robin Service. Deploy a **two-tier topology**: an Agent tier (or ingress proxy) routing spans via the OpenTelemetry **`loadbalancing` exporter** (keyed by `trace_id`) into the backend Gateway tier that runs `tail_sampling`.

---

## 6. Collector Self-Observability & Metrics Exposition

```yaml
  telemetry:
    metrics:
      readers:
        - pull:
            exporter:
              prometheus:
                host: 0.0.0.0
                port: 8888
```

* **Purpose:** Monitors the **collector container itself** (RAM usage, CPU, span queue drops, and export retry failures).
* **Format:** Exposes standard plain-text OpenMetrics/Prometheus format on `http://localhost:8888/metrics`.
* **Verification:** Run `curl http://localhost:8888/metrics` to inspect internal operational counters like `otelcol_receiver_accepted_spans` and `otelcol_exporter_sent_spans`.

---

## 7. Summary of Files Changed & Created

| File | Status | Description |
| :--- | :--- | :--- |
| [`telemetry/bootstrap.py`](wavefront/server/modules/common_module/common_module/telemetry/bootstrap.py) | **[NEW]** | Configures providers, instruments FastAPI, SQLAlchemy, Redis, and HTTPX. |
| [`telemetry/baggage_middleware.py`](wavefront/server/modules/common_module/common_module/telemetry/baggage_middleware.py) | **[NEW]** | Raw ASGI middleware injecting tenant metadata into context & `SERVER` span. |
| [`telemetry/baggage_span_processor.py`](wavefront/server/modules/common_module/common_module/telemetry/baggage_span_processor.py) | **[NEW]** | Promotes `app.*` baggage entries onto all child spans. |
| [`telemetry/errors.py`](wavefront/server/modules/common_module/common_module/telemetry/errors.py) | **[NEW]** | Attaches exception events and error status to active spans in global handlers. |
| [`otel/collector-base.yaml`](otel/collector-base.yaml) | **[NEW]** | Base OTel Collector config: receivers, processors, redaction, and local Jaeger pipeline. |
| [`otel/exporters/*.yaml`](otel/exporters/) | **[NEW]** | Additive cloud export overlays for Honeycomb, Generic OTLP, Azure, AWS, GCP, and None. |
| [`floware/server.py`](wavefront/server/apps/floware/floware/server.py) | **[MODIFY]** | Lifespan telemetry bootstrap, SQLAlchemy instrumentation, and Baggage middleware registration. |
| [`celery_app.py`](wavefront/server/background_jobs/celery_worker/celery_worker/celery_app.py) | **[MODIFY]** | Initializes OTel per worker process on `@worker_process_init.connect`. |
| [`common_module/pyproject.toml`](wavefront/server/modules/common_module/pyproject.toml) | **[MODIFY]** | Replaced `prometheus-client` with official `opentelemetry-*` packages. |
| [`prometheus_middleware.py`](wavefront/server/modules/common_module/common_module/prometheus/prometheus_middleware.py) | **[DELETED]** | Removed legacy Prometheus middleware. |
| [`docker-compose.local.yml`](docker-compose.local.yml) | **[MODIFY]** | Configured `otel-collector` (with overlay layer) and `jaeger` services. |
