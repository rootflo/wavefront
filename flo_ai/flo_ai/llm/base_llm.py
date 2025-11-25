from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, AsyncIterator
from flo_ai.tool.base_tool import Tool
from flo_ai.utils.document_processor import get_default_processor
from flo_ai.utils.logger import logger
from flo_ai.models.chat_message import DocumentMessageContent, ImageMessageContent


class BaseLLM(ABC):
    def __init__(
        self, model: str, api_key: str = None, temperature: float = 0.7, **kwargs
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
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream partial responses from the LLM as they are generated"""
        pass

    async def get_function_call(
        self, response: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Extract function call information from LLM response"""
        if hasattr(response, 'function_call') and response.function_call:
            result = {
                'name': response.function_call.name,
                'arguments': response.function_call.arguments,
            }
            # Include ID if available (LLM-specific)
            if hasattr(response.function_call, 'id'):
                result['id'] = response.function_call.id
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
    def format_image_in_message(self, image: ImageMessageContent) -> str:
        """Format a image in the message"""
        pass

    async def format_document_in_message(self, document: DocumentMessageContent) -> str:
        """Format a document in the message by extracting text content"""

        try:
            # Process document to extract text
            result = await get_default_processor().process_document(document)

            # Format the extracted content for the LLM
            extracted_text = result.get('extracted_text', '')
            doc_type = result.get('document_type', 'unknown')

            logger.info(
                f'Successfully formatted {doc_type} document for {self.__class__.__name__} LLM'
            )
            return extracted_text

        except Exception as e:
            logger.error(
                f'Error formatting document for {self.__class__.__name__}: {e}'
            )
            raise Exception(f'Failed to format document: {str(e)}')
