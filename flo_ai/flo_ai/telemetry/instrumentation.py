"""
Instrumentation utilities for flo_ai components
"""

from typing import Optional, Dict, Any, Callable
from functools import wraps
from opentelemetry.trace import Status, StatusCode, Span
from .telemetry import get_tracer, get_meter
import time
import asyncio


class LLMMetrics:
    """Metrics for LLM operations"""

    def __init__(self):
        self.meter = get_meter()
        if self.meter:
            # Token counters
            self.token_counter = self.meter.create_counter(
                name='llm.tokens.total',
                description='Total number of tokens used',
                unit='tokens',
            )

            self.prompt_tokens_counter = self.meter.create_counter(
                name='llm.tokens.prompt',
                description='Number of prompt tokens',
                unit='tokens',
            )

            self.completion_tokens_counter = self.meter.create_counter(
                name='llm.tokens.completion',
                description='Number of completion tokens',
                unit='tokens',
            )

            # Request counters
            self.request_counter = self.meter.create_counter(
                name='llm.requests.total',
                description='Total number of LLM requests',
                unit='requests',
            )

            self.error_counter = self.meter.create_counter(
                name='llm.errors.total',
                description='Total number of LLM errors',
                unit='errors',
            )

            # Latency histogram
            self.latency_histogram = self.meter.create_histogram(
                name='llm.request.duration',
                description='Duration of LLM requests',
                unit='ms',
            )

            # Streaming metrics
            self.stream_counter = self.meter.create_counter(
                name='llm.streams.total',
                description='Total number of LLM stream requests',
                unit='streams',
            )

            self.stream_chunks_counter = self.meter.create_counter(
                name='llm.stream.chunks.total',
                description='Total number of stream chunks received',
                unit='chunks',
            )

            self.stream_duration_histogram = self.meter.create_histogram(
                name='llm.stream.duration',
                description='Duration of LLM streaming requests',
                unit='ms',
            )

    def record_tokens(
        self,
        total_tokens: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        model: str = '',
        provider: str = '',
    ):
        """Record token usage"""
        if not self.meter:
            return

        attributes = {'model': model, 'provider': provider}

        if total_tokens > 0:
            self.token_counter.add(total_tokens, attributes)
        if prompt_tokens > 0:
            self.prompt_tokens_counter.add(prompt_tokens, attributes)
        if completion_tokens > 0:
            self.completion_tokens_counter.add(completion_tokens, attributes)

    def record_request(
        self, model: str = '', provider: str = '', status: str = 'success'
    ):
        """Record LLM request"""
        if not self.meter:
            return

        attributes = {'model': model, 'provider': provider, 'status': status}
        self.request_counter.add(1, attributes)

    def record_error(self, model: str = '', provider: str = '', error_type: str = ''):
        """Record LLM error"""
        if not self.meter:
            return

        attributes = {'model': model, 'provider': provider, 'error_type': error_type}
        self.error_counter.add(1, attributes)

    def record_latency(self, duration_ms: float, model: str = '', provider: str = ''):
        """Record request latency"""
        if not self.meter:
            return

        attributes = {'model': model, 'provider': provider}
        self.latency_histogram.record(duration_ms, attributes)

    def record_stream(
        self, model: str = '', provider: str = '', status: str = 'success'
    ):
        """Record LLM stream request"""
        if not self.meter:
            return

        attributes = {'model': model, 'provider': provider, 'status': status}
        self.stream_counter.add(1, attributes)

    def record_stream_chunks(
        self, chunk_count: int, model: str = '', provider: str = ''
    ):
        """Record stream chunks received"""
        if not self.meter:
            return

        attributes = {'model': model, 'provider': provider}
        self.stream_chunks_counter.add(chunk_count, attributes)

    def record_stream_latency(
        self, duration_ms: float, model: str = '', provider: str = ''
    ):
        """Record stream request latency"""
        if not self.meter:
            return

        attributes = {'model': model, 'provider': provider}
        self.stream_duration_histogram.record(duration_ms, attributes)


class AgentMetrics:
    """Metrics for Agent operations"""

    def __init__(self):
        self.meter = get_meter()
        if self.meter:
            # Execution counters
            self.execution_counter = self.meter.create_counter(
                name='agent.executions.total',
                description='Total number of agent executions',
                unit='executions',
            )

            self.tool_call_counter = self.meter.create_counter(
                name='agent.tool_calls.total',
                description='Total number of tool calls',
                unit='calls',
            )

            self.retry_counter = self.meter.create_counter(
                name='agent.retries.total',
                description='Total number of retries',
                unit='retries',
            )

            self.error_counter = self.meter.create_counter(
                name='agent.errors.total',
                description='Total number of agent errors',
                unit='errors',
            )

            # Latency histogram
            self.latency_histogram = self.meter.create_histogram(
                name='agent.execution.duration',
                description='Duration of agent executions',
                unit='ms',
            )

    def record_execution(
        self, agent_name: str = '', agent_type: str = '', status: str = 'success'
    ):
        """Record agent execution"""
        if not self.meter:
            return

        attributes = {
            'agent_name': agent_name,
            'agent_type': agent_type,
            'status': status,
        }
        self.execution_counter.add(1, attributes)

    def record_tool_call(
        self, agent_name: str = '', tool_name: str = '', status: str = 'success'
    ):
        """Record tool call"""
        if not self.meter:
            return

        attributes = {
            'agent_name': agent_name,
            'tool_name': tool_name,
            'status': status,
        }
        self.tool_call_counter.add(1, attributes)

    def record_retry(self, agent_name: str = '', reason: str = ''):
        """Record retry attempt"""
        if not self.meter:
            return

        attributes = {'agent_name': agent_name, 'reason': reason}
        self.retry_counter.add(1, attributes)

    def record_error(self, agent_name: str = '', error_type: str = ''):
        """Record agent error"""
        if not self.meter:
            return

        attributes = {'agent_name': agent_name, 'error_type': error_type}
        self.error_counter.add(1, attributes)

    def record_latency(
        self, duration_ms: float, agent_name: str = '', agent_type: str = ''
    ):
        """Record execution latency"""
        if not self.meter:
            return

        attributes = {'agent_name': agent_name, 'agent_type': agent_type}
        self.latency_histogram.record(duration_ms, attributes)


class WorkflowMetrics:
    """Metrics for Arium workflow operations"""

    def __init__(self):
        self.meter = get_meter()
        if self.meter:
            # Workflow counters
            self.workflow_counter = self.meter.create_counter(
                name='workflow.executions.total',
                description='Total number of workflow executions',
                unit='executions',
            )

            self.node_counter = self.meter.create_counter(
                name='workflow.nodes.executed',
                description='Total number of nodes executed',
                unit='nodes',
            )

            self.error_counter = self.meter.create_counter(
                name='workflow.errors.total',
                description='Total number of workflow errors',
                unit='errors',
            )

            # Latency histograms
            self.workflow_latency = self.meter.create_histogram(
                name='workflow.execution.duration',
                description='Duration of workflow executions',
                unit='ms',
            )

            self.node_latency = self.meter.create_histogram(
                name='workflow.node.duration',
                description='Duration of node executions',
                unit='ms',
            )

    def record_workflow(self, workflow_name: str = '', status: str = 'success'):
        """Record workflow execution"""
        if not self.meter:
            return

        attributes = {'workflow_name': workflow_name, 'status': status}
        self.workflow_counter.add(1, attributes)

    def record_node(
        self,
        workflow_name: str = '',
        node_name: str = '',
        node_type: str = '',
        status: str = 'success',
    ):
        """Record node execution"""
        if not self.meter:
            return

        attributes = {
            'workflow_name': workflow_name,
            'node_name': node_name,
            'node_type': node_type,
            'status': status,
        }
        self.node_counter.add(1, attributes)

    def record_error(self, workflow_name: str = '', error_type: str = ''):
        """Record workflow error"""
        if not self.meter:
            return

        attributes = {'workflow_name': workflow_name, 'error_type': error_type}
        self.error_counter.add(1, attributes)

    def record_workflow_latency(self, duration_ms: float, workflow_name: str = ''):
        """Record workflow latency"""
        if not self.meter:
            return

        attributes = {'workflow_name': workflow_name}
        self.workflow_latency.record(duration_ms, attributes)

    def record_node_latency(
        self,
        duration_ms: float,
        workflow_name: str = '',
        node_name: str = '',
        node_type: str = '',
    ):
        """Record node latency"""
        if not self.meter:
            return

        attributes = {
            'workflow_name': workflow_name,
            'node_name': node_name,
            'node_type': node_type,
        }
        self.node_latency.record(duration_ms, attributes)


# Global metric instances
llm_metrics = LLMMetrics()
agent_metrics = AgentMetrics()
workflow_metrics = WorkflowMetrics()


def trace_llm_call(provider: str = '', model: str = ''):
    """
    Decorator to trace LLM API calls

    Args:
        provider: LLM provider name (e.g., 'openai', 'anthropic', 'gemini')
        model: Model name

    Example:
        @trace_llm_call(provider="openai", model="gpt-4")
        async def generate(self, messages):
            ...
    """

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = get_tracer()
            if not tracer:
                return await func(*args, **kwargs)

            # Extract self to get instance attributes
            self_arg = args[0] if args else None
            actual_model = model or (getattr(self_arg, 'model', '') if self_arg else '')
            actual_provider = provider or (
                self_arg.__class__.__name__ if self_arg else ''
            )

            with tracer.start_as_current_span(
                f'llm.{actual_provider}.generate',
                attributes={
                    'llm.provider': actual_provider,
                    'llm.model': actual_model,
                    'llm.temperature': getattr(self_arg, 'temperature', 0.0)
                    if self_arg
                    else 0.0,
                },
            ) as span:
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)

                    # Record success
                    duration_ms = (time.time() - start_time) * 1000
                    llm_metrics.record_request(actual_model, actual_provider, 'success')
                    llm_metrics.record_latency(
                        duration_ms, actual_model, actual_provider
                    )

                    span.set_status(Status(StatusCode.OK))
                    span.set_attribute('llm.response.received', True)

                    return result

                except Exception as e:
                    # Record error
                    duration_ms = (time.time() - start_time) * 1000
                    error_type = type(e).__name__

                    llm_metrics.record_request(actual_model, actual_provider, 'error')
                    llm_metrics.record_error(actual_model, actual_provider, error_type)
                    llm_metrics.record_latency(
                        duration_ms, actual_model, actual_provider
                    )

                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute('error.type', error_type)
                    span.set_attribute('error.message', str(e))

                    raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = get_tracer()
            if not tracer:
                return func(*args, **kwargs)

            self_arg = args[0] if args else None
            actual_model = model or (getattr(self_arg, 'model', '') if self_arg else '')
            actual_provider = provider or (
                self_arg.__class__.__name__ if self_arg else ''
            )

            with tracer.start_as_current_span(
                f'llm.{actual_provider}.generate',
                attributes={
                    'llm.provider': actual_provider,
                    'llm.model': actual_model,
                },
            ) as span:
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)

                    duration_ms = (time.time() - start_time) * 1000
                    llm_metrics.record_request(actual_model, actual_provider, 'success')
                    llm_metrics.record_latency(
                        duration_ms, actual_model, actual_provider
                    )

                    span.set_status(Status(StatusCode.OK))
                    return result

                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    error_type = type(e).__name__

                    llm_metrics.record_request(actual_model, actual_provider, 'error')
                    llm_metrics.record_error(actual_model, actual_provider, error_type)
                    llm_metrics.record_latency(
                        duration_ms, actual_model, actual_provider
                    )

                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute('error.type', error_type)

                    raise

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def trace_llm_stream(provider: str = '', model: str = ''):
    """
    Decorator to trace LLM streaming API calls

    Args:
        provider: LLM provider name (e.g., 'openai', 'anthropic', 'gemini')
        model: Model name

    Example:
        @trace_llm_stream(provider="openai", model="gpt-4")
        async def stream(self, messages):
            ...
    """

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = get_tracer()
            if not tracer:
                async for chunk in func(*args, **kwargs):
                    yield chunk
                return

            # Extract self to get instance attributes
            self_arg = args[0] if args else None
            actual_model = model or (getattr(self_arg, 'model', '') if self_arg else '')
            actual_provider = provider or (
                self_arg.__class__.__name__ if self_arg else ''
            )

            with tracer.start_as_current_span(
                f'llm.{actual_provider}.stream',
                attributes={
                    'llm.provider': actual_provider,
                    'llm.model': actual_model,
                    'llm.temperature': getattr(self_arg, 'temperature', 0.0)
                    if self_arg
                    else 0.0,
                    'llm.operation': 'stream',
                },
            ) as span:
                start_time = time.time()
                chunk_count = 0
                try:
                    # Record stream start
                    llm_metrics.record_stream(actual_model, actual_provider, 'start')

                    # Track the streaming response
                    async for chunk in func(*args, **kwargs):
                        chunk_count += 1
                        yield chunk

                    # Record success
                    duration_ms = (time.time() - start_time) * 1000
                    llm_metrics.record_stream(actual_model, actual_provider, 'success')
                    llm_metrics.record_stream_chunks(
                        chunk_count, actual_model, actual_provider
                    )
                    llm_metrics.record_stream_latency(
                        duration_ms, actual_model, actual_provider
                    )

                    span.set_status(Status(StatusCode.OK))
                    span.set_attribute('llm.stream.chunks', chunk_count)
                    span.set_attribute('llm.stream.duration_ms', duration_ms)
                    span.set_attribute('llm.stream.completed', True)

                except Exception as e:
                    # Record error
                    duration_ms = (time.time() - start_time) * 1000
                    error_type = type(e).__name__

                    llm_metrics.record_stream(actual_model, actual_provider, 'error')
                    llm_metrics.record_error(actual_model, actual_provider, error_type)
                    llm_metrics.record_stream_latency(
                        duration_ms, actual_model, actual_provider
                    )

                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute('error.type', error_type)
                    span.set_attribute('error.message', str(e))
                    span.set_attribute('llm.stream.chunks', chunk_count)
                    span.set_attribute('llm.stream.duration_ms', duration_ms)

                    raise

        return async_wrapper

    return decorator


def trace_agent_execution(agent_name: str = ''):
    """
    Decorator to trace agent executions

    Args:
        agent_name: Name of the agent

    Example:
        @trace_agent_execution(agent_name="research_agent")
        async def run(self, inputs):
            ...
    """

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = get_tracer()
            if not tracer:
                return await func(*args, **kwargs)

            self_arg = args[0] if args else None
            actual_agent_name = agent_name or (
                getattr(self_arg, 'name', '') if self_arg else ''
            )
            agent_type = getattr(self_arg, 'agent_type', '') if self_arg else ''

            with tracer.start_as_current_span(
                f'agent.{actual_agent_name}.run',
                attributes={
                    'agent.name': actual_agent_name,
                    'agent.type': str(agent_type),
                },
            ) as span:
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)

                    duration_ms = (time.time() - start_time) * 1000
                    agent_metrics.record_execution(
                        actual_agent_name, str(agent_type), 'success'
                    )
                    agent_metrics.record_latency(
                        duration_ms, actual_agent_name, str(agent_type)
                    )

                    span.set_status(Status(StatusCode.OK))
                    span.set_attribute(
                        'agent.result.length', len(str(result)) if result else 0
                    )

                    return result

                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    error_type = type(e).__name__

                    agent_metrics.record_execution(
                        actual_agent_name, str(agent_type), 'error'
                    )
                    agent_metrics.record_error(actual_agent_name, error_type)
                    agent_metrics.record_latency(
                        duration_ms, actual_agent_name, str(agent_type)
                    )

                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute('error.type', error_type)

                    raise

        return async_wrapper

    return decorator


def add_span_attributes(span: Optional[Span], attributes: Dict[str, Any]) -> None:
    """
    Helper to add attributes to a span safely

    Args:
        span: OpenTelemetry span
        attributes: Dictionary of attributes to add
    """
    if span and attributes:
        for key, value in attributes.items():
            # OpenTelemetry only supports certain types
            if isinstance(value, (str, bool, int, float)):
                span.set_attribute(key, value)
            else:
                span.set_attribute(key, str(value))
