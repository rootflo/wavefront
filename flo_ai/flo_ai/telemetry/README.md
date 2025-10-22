# OpenTelemetry Integration for flo_ai

This module provides comprehensive OpenTelemetry integration for the flo_ai framework, enabling you to monitor and track:

- 🔍 **LLM Calls**: Track token usage, latency, and errors across different providers
- 🤖 **Agent Execution**: Monitor agent performance, tool calls, and retry attempts
- 🔄 **Workflows**: Track workflow execution, node traversals, and bottlenecks
- 📊 **Metrics**: Export performance metrics to your observability platform

## Quick Start

### 1. Installation

The telemetry dependencies are included in flo_ai. Install with:

```bash
pip install flo_ai
```

### 2. Basic Configuration

```python
from flo_ai import configure_telemetry, shutdown_telemetry

# Configure at the start of your application
configure_telemetry(
    service_name="my_ai_app",
    service_version="1.0.0",
    console_export=True  # For debugging
)

# ... your application code ...

# Shutdown at the end to flush data
shutdown_telemetry()
```

### 3. Export to OTLP Collector

```python
configure_telemetry(
    service_name="my_ai_app",
    otlp_endpoint="http://localhost:4317",  # Your OTLP collector
    console_export=False
)
```

## Features

### Automatic Instrumentation

Once configured, telemetry is automatically captured for:

#### LLM Calls
- Request duration (latency)
- Token usage (prompt, completion, total)
- Model and provider information
- Success/error rates
- **Streaming support**: Chunk count, stream duration, streaming success rates

#### Agent Execution
- Total execution time
- Number of tool calls
- Retry attempts
- Conversation history size

#### Workflows (Arium)
- End-to-end workflow duration
- Individual node execution times
- Router decisions
- Node success/failure rates

### Metrics Collected

#### LLM Metrics
- `llm.tokens.total` - Total tokens used
- `llm.tokens.prompt` - Prompt tokens
- `llm.tokens.completion` - Completion tokens
- `llm.requests.total` - Number of LLM requests
- `llm.errors.total` - Number of errors
- `llm.request.duration` - Request latency histogram
- `llm.streams.total` - Number of LLM stream requests
- `llm.stream.chunks.total` - Total number of stream chunks received
- `llm.stream.duration` - Stream request latency histogram

#### Agent Metrics
- `agent.executions.total` - Number of agent executions
- `agent.tool_calls.total` - Number of tool calls
- `agent.retries.total` - Number of retries
- `agent.errors.total` - Number of errors
- `agent.execution.duration` - Execution time histogram

#### Workflow Metrics
- `workflow.executions.total` - Number of workflow executions
- `workflow.nodes.executed` - Number of nodes executed
- `workflow.errors.total` - Number of errors
- `workflow.execution.duration` - Workflow execution time
- `workflow.node.duration` - Node execution time

### Spans (Traces)

Spans are automatically created for:
- `llm.{provider}.generate` - LLM API calls
- `agent.{name}.run` - Agent executions
- `agent.tool.{name}` - Tool executions
- `workflow.{name}` - Workflow executions
- `workflow.node.{name}` - Node executions

## Configuration Options

### Environment Variables

- `FLO_ENV` - Environment name (default: "development")
- `FLO_OTLP_ENDPOINT` - OTLP endpoint URL

### Configuration Parameters

```python
configure_telemetry(
    service_name: str = "flo_ai",              # Service name for telemetry
    service_version: str = "1.0.0",            # Service version
    environment: str = None,                    # Environment (dev/staging/prod)
    otlp_endpoint: str = None,                  # OTLP collector endpoint
    console_export: bool = False,               # Export to console
    additional_attributes: Dict[str, Any] = None # Custom resource attributes
)
```

## Integration Examples

### With Jaeger

```bash
# Start Jaeger
docker run -d --name jaeger \
  -e COLLECTOR_OTLP_ENABLED=true \
  -p 16686:16686 \
  -p 4317:4317 \
  jaegertracing/all-in-one:latest
```

```python
configure_telemetry(
    service_name="my_app",
    otlp_endpoint="http://localhost:4317"
)
```

View traces at http://localhost:16686

### With Prometheus & Grafana

```python
# Use OTLP exporter pointing to your collector
configure_telemetry(
    service_name="my_app",
    otlp_endpoint="http://otel-collector:4317"
)
```

### With Cloud Providers

#### AWS X-Ray
```python
# Use OTLP with AWS Distro for OpenTelemetry
configure_telemetry(
    service_name="my_app",
    otlp_endpoint="http://aws-otel-collector:4317"
)
```

#### Google Cloud Trace
```python
# Use Cloud Trace exporter
configure_telemetry(
    service_name="my_app",
    otlp_endpoint="http://localhost:4317",  # Cloud Ops collector
    additional_attributes={
        "gcp.project_id": "your-project-id"
    }
)
```

#### Azure Monitor
```python
# Use Azure Monitor OTLP endpoint
configure_telemetry(
    service_name="my_app",
    otlp_endpoint="https://<your-instance>.monitor.azure.com/opentelemetry/v1/traces"
)
```

## Advanced Usage

### Custom Spans

```python
from flo_ai import get_tracer

tracer = get_tracer()
if tracer:
    with tracer.start_as_current_span("custom_operation") as span:
        span.set_attribute("custom.attribute", "value")
        # Your code here
```

### Custom Metrics

```python
from flo_ai import get_meter

meter = get_meter()
if meter:
    # Create a counter
    my_counter = meter.create_counter(
        name="my_custom_counter",
        description="Custom operation counter",
        unit="operations"
    )
    my_counter.add(1, {"operation": "custom"})
    
    # Create a histogram
    my_histogram = meter.create_histogram(
        name="my_custom_duration",
        description="Custom operation duration",
        unit="ms"
    )
    my_histogram.record(123.45, {"operation": "custom"})
```

### Filtering Telemetry

To disable telemetry temporarily:

```python
# Don't call configure_telemetry()
# The framework will detect no telemetry is configured and skip instrumentation
```

## Best Practices

### 1. Configure Once at Startup

```python
def initialize_app():
    configure_telemetry(
        service_name="my_app",
        otlp_endpoint=os.getenv("OTLP_ENDPOINT"),
        environment=os.getenv("ENV", "development")
    )
```

### 2. Always Shutdown on Exit

```python
import atexit
from flo_ai import shutdown_telemetry

atexit.register(shutdown_telemetry)
```

### 3. Use Meaningful Service Names

```python
configure_telemetry(
    service_name="customer-support-bot",  # Specific and descriptive
    service_version="2.1.0"
)
```

### 4. Add Context with Attributes

```python
configure_telemetry(
    service_name="my_app",
    additional_attributes={
        "deployment.region": "us-west-2",
        "team": "ml-platform",
        "environment.type": "production"
    }
)
```

### 5. Monitor Key Metrics

Focus on:
- Token usage trends (cost monitoring)
- LLM latency (performance)
- Error rates (reliability)
- Agent execution times (user experience)

## Performance Impact

The telemetry instrumentation has minimal performance overhead:

- **LLM calls**: < 1ms additional latency
- **Agent execution**: < 2ms overhead
- **Workflow execution**: < 5ms overhead
- **Memory**: ~10MB for buffering spans/metrics

Metrics are exported asynchronously and don't block your application.

## Troubleshooting

### No Data Appearing

1. Check OTLP endpoint is accessible:
   ```bash
   curl http://localhost:4317
   ```

2. Enable console export for debugging:
   ```python
   configure_telemetry(console_export=True)
   ```

3. Ensure shutdown is called:
   ```python
   shutdown_telemetry()
   ```

### High Memory Usage

If you see high memory usage:

1. Reduce export interval (default is 5 seconds)
2. Ensure shutdown is called to flush buffers
3. Check your OTLP collector is accepting data

### Missing Token Metrics

Token metrics are only available for providers that return usage data:
- ✅ OpenAI (full support)
- ✅ Anthropic (full support)
- ✅ Gemini (full support)
- ⚠️  Ollama (limited support)

## Examples

See the [telemetry_example.py](../../examples/telemetry_example.py) file for complete examples including:

- Basic agent with LLM telemetry
- Agent with tool calls
- Workflow telemetry with Arium
- Multiple LLM providers
- Error tracking

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Your Application                     │
├─────────────────────────────────────────────────────────┤
│  Agent.run() → @trace_agent_execution                   │
│  LLM.generate() → @trace_llm_call                       │
│  Workflow.run() → telemetry tracking                    │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│              OpenTelemetry SDK                          │
│  • Tracer Provider (spans/traces)                       │
│  • Meter Provider (metrics)                             │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│                   Exporters                             │
│  • OTLP Exporter → Collector/Backend                    │
│  • Console Exporter → stdout                            │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│              Observability Platforms                     │
│  Jaeger, Prometheus, Grafana, Cloud Providers, etc.     │
└─────────────────────────────────────────────────────────┘
```

## Contributing

To add telemetry to new components:

1. Import instrumentation utilities:
   ```python
   from flo_ai.telemetry.instrumentation import trace_llm_call, agent_metrics
   from flo_ai.telemetry import get_tracer
   ```

2. Add decorators or manual instrumentation
3. Record metrics using the appropriate metrics instance
4. Add span attributes for context

## License

This telemetry module is part of flo_ai and follows the same MIT license.

