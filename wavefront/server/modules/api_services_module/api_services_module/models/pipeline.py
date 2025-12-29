"""Pipeline models and protocols."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field
import uuid
from datetime import datetime


class StageType(Enum):
    """Pipeline stage types."""

    AUTHENTICATOR = 'authenticator'
    HEADER_INJECTOR = 'header_injector'
    API_PROCESSOR = 'api_processor'
    PAYLOAD_VALIDATOR = 'payload_validator'
    REQUEST_SENDER = 'request_sender'
    RESPONSE_MAPPER = 'response_mapper'
    COMPOSITE = 'composite'


@dataclass
class PipelineContext:
    """Context object that flows through pipeline stages."""

    # Request information
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    service_id: str = ''
    api_id: str = ''
    api_version: str = 'v1'
    method: str = 'POST'
    path: str = ''
    path_params: Dict[str, str] = field(
        default_factory=dict
    )  # Path parameters extracted from URL
    query_params: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[Any] = None

    # Authentication context
    auth_config: Dict[str, Any] = field(default_factory=dict)
    auth_headers: Dict[str, str] = field(default_factory=dict)

    # Backend information
    backend_url: str = ''
    backend_path: str = ''
    backend_headers: Dict[str, str] = field(default_factory=dict)

    # Response information
    response_status: Optional[int] = None
    response_headers: Dict[str, str] = field(default_factory=dict)
    response_body: Optional[Any] = None
    is_binary_response: bool = False  # Flag to indicate binary content
    raw_response_content: Optional[bytes] = None  # Raw bytes for binary responses

    # Execution trace
    execution_trace: List[str] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)

    def add_trace(self, stage_name: str, message: str = ''):
        """Add execution trace entry."""
        timestamp = datetime.now().isoformat()
        trace_entry = f'[{timestamp}] {stage_name}'
        if message:
            trace_entry += f': {message}'
        self.execution_trace.append(trace_entry)

    def merge_headers(self, new_headers: Dict[str, str]):
        """Merge new headers with existing headers."""
        self.headers.update(new_headers)

    def merge_backend_headers(self, new_headers: Dict[str, str]):
        """Merge new headers with backend headers."""
        self.backend_headers.update(new_headers)


class PipelineException(Exception):
    """Exception raised during pipeline execution."""

    def __init__(
        self,
        message: str,
        stage_name: str = '',
        context: Optional[PipelineContext] = None,
    ):
        self.message = message
        self.stage_name = stage_name
        self.context = context
        super().__init__(message)


class PipelineStage(ABC):
    """
    Abstract base class for all pipeline components.

    All pipeline stages (atomic and composite) must implement this protocol.
    This ensures uniform behavior across the entire pipeline architecture.
    """

    @abstractmethod
    async def execute(self, context: PipelineContext) -> PipelineContext:
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
        """Get the type of this pipeline stage."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get the name/identifier of this pipeline stage."""
        pass


class CompositePipelineStage(PipelineStage):
    """
    Composite pipeline stage that executes multiple stages in sequence.

    Implements the Composite pattern for building complex pipelines
    from simpler components.
    """

    def __init__(self, name: str, stages: List[PipelineStage]):
        self.name = name
        self.stages = stages

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """Execute all stages in sequence."""
        context.add_trace(
            self.get_name(),
            f'Starting composite pipeline with {len(self.stages)} stages',
        )

        try:
            for stage in self.stages:
                context = await stage.execute(context)

            context.add_trace(
                self.get_name(), 'Composite pipeline completed successfully'
            )
            return context

        except Exception as e:
            context.add_trace(self.get_name(), f'Composite pipeline failed: {str(e)}')
            if isinstance(e, PipelineException):
                raise
            else:
                raise PipelineException(
                    f"Composite pipeline '{self.name}' failed: {str(e)}",
                    self.get_name(),
                    context,
                )

    def get_stage_type(self) -> StageType:
        """Return composite stage type."""
        return StageType.COMPOSITE

    def get_name(self) -> str:
        """Return the composite pipeline name."""
        return self.name

    def add_stage(self, stage: PipelineStage):
        """Add a stage to the pipeline."""
        self.stages.append(stage)

    def remove_stage(self, stage_name: str) -> bool:
        """Remove a stage by name. Returns True if removed, False if not found."""
        for i, stage in enumerate(self.stages):
            if stage.get_name() == stage_name:
                self.stages.pop(i)
                return True
        return False
