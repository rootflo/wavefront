from opentelemetry import trace
from opentelemetry.trace import Status
from opentelemetry.trace import StatusCode


def record_exception_on_span(exc: BaseException, *, escaped: bool = False) -> None:
    """Attach an exception to the active span and mark the span as errored.

    Exceptions that propagate out of a request are recorded automatically by the
    FastAPI instrumentation, so this is only needed for exceptions that are
    caught and turned into an error response without ever being re-raised —
    those would otherwise leave the span looking like a success.

    Records ``exception.type``, ``exception.message`` and
    ``exception.stacktrace`` as a span event, per the OpenTelemetry semantic
    conventions.
    """
    span = trace.get_current_span()
    if not span.is_recording():
        return

    span.record_exception(exc, escaped=escaped)
    span.set_status(Status(StatusCode.ERROR, str(exc)))
