from typing import Optional

from opentelemetry import baggage
from opentelemetry.context import Context
from opentelemetry.sdk.trace import Span
from opentelemetry.sdk.trace import SpanProcessor


class BaggageSpanProcessor(SpanProcessor):
    """Promotes ``app.*`` baggage entries onto every span as attributes.

    OpenTelemetry baggage travels on the context and the ``baggage`` header but
    is never recorded on spans automatically. This processor copies the business
    context established by ``BaggageMiddleware`` onto each span as it starts, so
    DB, cache, HTTP-client and LLM child spans all carry it without any call
    site having to thread it through manually.

    Only the ``app.`` prefix is promoted, which keeps arbitrary inbound baggage
    from third parties out of our telemetry.
    """

    def __init__(self, prefix: str = 'app.') -> None:
        self._prefix = prefix

    def on_start(self, span: Span, parent_context: Optional[Context] = None) -> None:
        for key, value in baggage.get_all(context=parent_context).items():
            if key.startswith(self._prefix) and value is not None:
                span.set_attribute(key, str(value))

    def on_end(self, span: Span) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True
