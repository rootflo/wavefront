import asyncio
import base64 as _base64
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, AsyncIterator
from flo_ai.tool.base_tool import Tool
from flo_ai.utils.logger import logger
from flo_ai.utils.profiler import aprofile, profile as _sync_profile
from flo_ai.models.chat_message import DocumentMessageContent, ImageMessageContent


class BaseLLM(ABC):
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
        """Return provider-native content block(s) for a document.

        Default implementation rasterizes PDF pages to PNG ``image_url``
        blocks in the OpenAI Chat Completions multimodal shape. This assumes
        the underlying model is vision-capable (gpt-4o, gpt-4.1, gpt-5,
        llava, etc.). LLMs that do not support image inputs will error at
        request time — intentionally; the library does not ship a
        text-extraction fallback because it silently hides capability
        mismatches and usually produces worse results than using a vision
        model.

        Providers with native PDF support (Anthropic, Gemini, Vertex, the
        OpenAI Responses API, etc.) override this to return their native
        document block. Results are cached on the DocumentMessageContent per
        LLM class so the same document is formatted at most once across all
        agent nodes and retries in a workflow.
        """
        cache_key = self.__class__.__name__
        cache = getattr(document, '_formatted_cache', None)
        if isinstance(cache, dict) and cache_key in cache:
            return cache[cache_key]

        async with aprofile(f'llm.{cache_key}.format_document'):
            try:
                formatted = await asyncio.to_thread(
                    self._rasterize_pdf_to_images, document
                )
            except Exception as e:
                logger.error(
                    f'Error formatting document for {self.__class__.__name__}: {e}'
                )
                raise Exception(f'Failed to format document: {str(e)}')

        if isinstance(cache, dict):
            cache[cache_key] = formatted
        return formatted

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
