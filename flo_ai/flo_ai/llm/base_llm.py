import asyncio
import base64 as _base64
import inspect
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import (
    Callable,
    Dict,
    Any,
    Iterable,
    List,
    Mapping,
    Optional,
    AsyncIterator,
    Tuple,
)
from flo_ai.helpers.generation_params import merge_generation_params
from flo_ai.tool.base_tool import Tool
from flo_ai.utils.document_text_extraction import (
    EXTRACTABLE_DOCUMENT_MIME_TYPES,
    extract_document_text,
)
from flo_ai.utils.logger import logger
from flo_ai.utils.profiler import aprofile, profile as _sync_profile
from flo_ai.models.chat_message import (
    DocumentMessageContent,
    ImageMessageContent,
    MediaMessageContent,
)


def split_client_kwargs(
    client_cls: type, kwargs: Dict[str, Any], reserved: Iterable[str] = ()
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Split a wrapper's extra kwargs into SDK client options and request params.

    Extra kwargs are how a caller sets generation params for every request
    (top_p, seed, max_completion_tokens), which generate() and stream() spread
    into the request body. A few are client options instead (timeout,
    max_retries, http_client), and the SDK constructors declare no catch-all
    **kwargs, so handing one a generation param raises TypeError. Matching the
    client's own signature keeps that split from needing a maintained list.

    Args:
        client_cls: The SDK client class the wrapper instantiates
        kwargs: The extra kwargs the wrapper was constructed with
        reserved: Names the wrapper passes to the client itself, dropped
            because passing them twice is a TypeError

    Returns:
        Tuple of (client options, request params)
    """
    client_params = inspect.signature(client_cls.__init__).parameters
    reserved = set(reserved)

    client_kwargs: Dict[str, Any] = {}
    request_kwargs: Dict[str, Any] = {}
    for key, value in kwargs.items():
        if key in reserved:
            continue
        target = client_kwargs if key in client_params else request_kwargs
        target[key] = value

    return client_kwargs, request_kwargs


@lru_cache(maxsize=16)
def _declared_params(func: Callable[..., Any]) -> Tuple[frozenset, bool]:
    """The parameter names `func` declares, and whether it takes **kwargs."""
    params = inspect.signature(func).parameters
    accepts_any = any(
        param.kind is inspect.Parameter.VAR_KEYWORD for param in params.values()
    )
    return frozenset(params), accepts_any


def flatten_extra_body(params: Mapping[str, Any]) -> Dict[str, Any]:
    """`extra_body` entries spelled out as ordinary request params.

    The two forms mean the same thing, so keeping them apart loses precedence:
    once an instance's params and a call's params are merged into one mapping,
    there is no way to tell whether `extra_body={'top_k': 9}` or a bare
    `top_k=5` came from the later layer. Flattening each layer *before* merging
    makes the later one win whichever form it used, and stops a per-call
    `extra_body` replacing the instance's wholesale instead of merging with it.

    Within a single layer an `extra_body` entry wins over a bare key of the same
    name. Writing both in one call is ambiguous either way, and the escape hatch
    is the more deliberate of the two.

    Args:
        params: One layer's request params

    Returns:
        The same params with no `extra_body` key
    """
    flat = {key: value for key, value in params.items() if key != 'extra_body'}
    flat.update(params.get('extra_body') or {})
    return flat


def split_request_kwargs(
    create_method: Callable[..., Any], kwargs: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Split request params into ones the SDK declares and ones needing extra_body.

    The OpenAI SDK's create() declares no **kwargs, so a param outside its
    signature - vLLM's `top_k`, or an inference server's own knobs - raises
    TypeError locally instead of reaching the server that understands it.
    `extra_body` is the SDK's own escape hatch: its contents are merged into the
    request body verbatim, which is where an OpenAI-compatible server looks.

    Args:
        create_method: The SDK method the wrapper calls (bound or unbound)
        kwargs: Request params to be sent

    Returns:
        Tuple of (params create() declares, params for extra_body)
    """
    names, accepts_any = _declared_params(
        getattr(create_method, '__func__', create_method)
    )
    if accepts_any:
        return dict(kwargs), {}

    declared: Dict[str, Any] = {}
    extra: Dict[str, Any] = {}
    for key, value in kwargs.items():
        target = declared if key in names else extra
        target[key] = value

    return declared, extra


def _normalized_mime(document: DocumentMessageContent) -> Optional[str]:
    """Lowercased mime type with any ``;charset=...`` parameters dropped.

    Callers pass whatever the upload declared. ``TEXT/CSV; charset=utf-8`` has
    to route the same way as ``text/csv``, or the choice between extracting and
    rasterizing turns on capitalization.
    """
    if not document.mime_type:
        return None
    return document.mime_type.split(';')[0].strip().lower() or None


def file_name_text_block(media: MediaMessageContent) -> Optional[Dict[str, Any]]:
    """An OpenAI-shaped text block naming the file, or None if unnamed.

    Agents are routinely asked to report the original filename of a document
    they were given, and nothing else in the request carries it — the media
    block is just bytes plus a mime type. Without this the model has no
    source for the name and invents a plausible-looking one.

    Prepended to the media block within the *same* message rather than sent
    as its own message: a ForEach that iterates over the input messages
    counts one item per message, so an extra message per file would double
    the iterations.
    """
    if not media.file_name:
        return None
    return {'type': 'text', 'text': f'Original filename: {media.file_name}'}


class BaseLLM(ABC):
    # Which provider's wire names this wrapper's request params use. Read when
    # translating canonical generation params; see llm.generation_params.
    provider_name: str = ''

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs,
    ):
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.kwargs = kwargs

    def __copy__(self) -> 'BaseLLM':
        """A copy whose per-agent settings are independent of this instance's.

        AgentBuilder copies rather than mutates the LLM it is handed, so a
        base_llm shared between agents does not take on one agent's temperature
        or generation params. `kwargs` is copied for the same reason - it holds
        those params. The SDK client is deliberately shared: it carries the
        connection pool and nothing per-agent.
        """
        clone = self.__class__.__new__(self.__class__)
        clone.__dict__.update(self.__dict__)
        clone.kwargs = dict(self.kwargs)
        return clone

    def apply_generation_params(self, params: Dict[str, Any]) -> None:
        """Merge canonically-named generation params into every request.

        Applied on top of whatever the LLM was constructed with, so an agent's
        YAML `settings:` outranks the LLM inference config it resolved from -
        including when the two name the token limit differently.

        Args:
            params: Canonical names (`max_tokens`, `top_p`, ...), translated
                here to the spellings this provider's API accepts
        """
        self.kwargs = merge_generation_params(self.kwargs, params, self.provider_name)

    @abstractmethod
    async def generate(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate a response from the LLM"""
        pass

    @abstractmethod
    async def stream(
        self,
        messages: List[Dict[str, str]],
        functions: Optional[List[Dict[str, Any]]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream partial responses from the LLM as they are generated"""
        pass

    async def get_function_call(
        self, response: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Extract function call information from LLM response"""
        if hasattr(response, 'function_call') and response.function_call:
            function_call = response.function_call
            if hasattr(function_call, 'name') and hasattr(function_call, 'arguments'):
                result = {
                    'name': function_call.name,
                    'arguments': function_call.arguments,
                }
                # Include ID if available (LLM-specific)
                if hasattr(function_call, 'id'):
                    result['id'] = function_call.id
                return result

        elif isinstance(response, dict) and 'function_call' in response:
            result = {
                'name': response['function_call']['name'],
                'arguments': response['function_call']['arguments'],
            }
            # Include ID if available (LLM-specific)
            if 'id' in response['function_call']:
                result['id'] = response['function_call']['id']
            return result
        return None

    def get_assistant_message_for_tool_call(
        self, response: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Get the assistant message content for tool calls.
        Override in LLM-specific implementations if special handling is needed.
        Returns None to use default text content extraction.
        """
        return None

    def get_tool_use_id(self, function_call: Dict[str, Any]) -> Optional[str]:
        """
        Extract tool_use_id from function call if available.
        Override in LLM-specific implementations if IDs are used.
        Returns None by default.
        """
        return function_call.get('id')

    def format_function_result_message(
        self, function_name: str, content: str, tool_use_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Format a function result message for the LLM.
        Override in LLM-specific implementations for special formatting.
        """
        message = {
            'role': 'function',
            'name': function_name,
            'content': content,
        }
        if tool_use_id:
            message['tool_use_id'] = tool_use_id
        return message

    @abstractmethod
    def get_message_content(self, response: Dict[str, Any]) -> str:
        """Extract message content from response"""
        pass

    @abstractmethod
    def format_tool_for_llm(self, tool: 'Tool') -> Dict[str, Any]:
        """Format a tool for the specific LLM's API"""
        pass

    @abstractmethod
    def format_tools_for_llm(self, tools: List['Tool']) -> List[Dict[str, Any]]:
        """Format a list of tools for the specific LLM's API"""
        pass

    @abstractmethod
    def format_image_in_message(self, image: ImageMessageContent) -> Any:
        """Format a image in the message"""
        pass

    async def format_document_in_message(self, document: DocumentMessageContent) -> Any:
        """Return provider-ready content for a document.

        Two paths, chosen by mime type:

        - Office and plain-text formats (``EXTRACTABLE_DOCUMENT_MIME_TYPES``)
          are converted to text and wrapped by ``format_text_content``. No
          provider flo_ai supports reads Word or Excel through the API shape
          flo_ai uses, so the alternative is failing the request outright.
        - Everything else -- PDF, and a missing mime, which is assumed to be
          PDF -- goes to ``_format_native_document``: a native document block
          where the provider has one, rasterized pages where it does not.

        PDF is never extracted. A vision model reading the page beats extracted
        text for PDFs, and silently downgrading would hide the capability
        mismatch when a model cannot read images at all.

        Results are cached on the DocumentMessageContent per LLM class, so the
        same document is formatted at most once across all agent nodes and
        retries in a workflow. Subclasses override ``_format_native_document``
        and ``format_text_content`` rather than this method, so every provider
        inherits both the dispatch and the cache.
        """
        cache_key = self.__class__.__name__
        cache = getattr(document, '_formatted_cache', None)
        if isinstance(cache, dict) and cache_key in cache:
            return cache[cache_key]

        async with aprofile(f'llm.{cache_key}.format_document'):
            if _normalized_mime(document) in EXTRACTABLE_DOCUMENT_MIME_TYPES:
                formatted = await asyncio.to_thread(
                    self._format_extracted_document, document
                )
            else:
                formatted = await self._format_native_document(document)

        if isinstance(cache, dict):
            cache[cache_key] = formatted
        return formatted

    def _format_extracted_document(self, document: DocumentMessageContent) -> Any:
        """Convert an Office or plain-text document to a text content block.

        ``DocumentExtractionError`` is deliberately not wrapped: it means the
        upload itself is unreadable, which a caller needs to tell apart from a
        provider failure so it can report it to whoever sent the file.
        """
        text = extract_document_text(
            self._document_to_bytes(document),
            _normalized_mime(document),
            document.file_name,
        )
        return self.format_text_content(text)

    def format_text_content(self, text: str) -> Any:
        """Wrap plain text in this provider's content-block shape.

        The default is the OpenAI Chat Completions shape, which Anthropic
        shares. Providers with a different shape (Gemini's ``Part``) override.
        """
        return [{'type': 'text', 'text': text}]

    async def _format_native_document(self, document: DocumentMessageContent) -> Any:
        """Format a PDF (or unknown-mime) document the provider's native way.

        The default rasterizes PDF pages to PNG ``image_url`` blocks in the
        OpenAI Chat Completions multimodal shape. This assumes a vision-capable
        model (gpt-4o, gpt-4.1, gpt-5, llava, etc.); a model without image
        input errors at request time -- intentionally, rather than quietly
        falling back to extracted text.

        Providers with native PDF support (Anthropic, Gemini, Vertex, the
        OpenAI Responses API, etc.) override this to return their native
        document block. Caching is handled by the caller.
        """
        try:
            return await asyncio.to_thread(self._rasterize_pdf_to_images, document)
        except Exception as e:
            logger.error(
                f'Error formatting document for {self.__class__.__name__}: {e}'
            )
            raise Exception(f'Failed to format document: {str(e)}')

    def _rasterize_pdf_to_images(
        self, document: DocumentMessageContent
    ) -> List[Dict[str, Any]]:
        """Rasterize a PDF to a list of OpenAI-style image_url blocks.

        Uses plain PyMuPDF (no pymupdf4llm). Skips text-extraction / table
        detection entirely — vision-capable models read the page image
        directly. DPI is configurable via the LLM kwargs `pdf_raster_dpi`
        (default 150).
        """
        import pymupdf

        data = self._document_to_bytes(document)
        mime = document.mime_type or 'application/pdf'
        if not mime.endswith('pdf'):
            raise ValueError(
                f'Default document formatter only supports PDFs, got mime={mime}. '
                f'Override format_document_in_message for {self.__class__.__name__}.'
            )

        dpi = int((getattr(self, 'kwargs', None) or {}).get('pdf_raster_dpi', 150))
        doc = pymupdf.open(stream=data, filetype='pdf')
        try:
            blocks: List[Dict[str, Any]] = []
            for page_idx in range(doc.page_count):
                page = doc.load_page(page_idx)
                with _sync_profile(f'pdf.rasterize_page[dpi={dpi},page={page_idx}]'):
                    pix = page.get_pixmap(dpi=dpi)
                    png_bytes = pix.tobytes('png')
                    b64 = _base64.b64encode(png_bytes).decode('utf-8')
                blocks.append(
                    {
                        'type': 'image_url',
                        'image_url': {'url': f'data:image/png;base64,{b64}'},
                    }
                )
            return blocks
        finally:
            doc.close()

    @staticmethod
    def _document_to_bytes(document: DocumentMessageContent) -> bytes:
        """Resolve a DocumentMessageContent to raw bytes."""
        if document.bytes:
            return document.bytes
        if document.base64:
            return _base64.b64decode(document.base64)
        if document.url:
            raise ValueError(
                'URL-based documents are not supported by the default formatter; '
                'fetch the document bytes first or override format_document_in_message.'
            )
        raise ValueError('DocumentMessageContent has no bytes, base64, or url')
