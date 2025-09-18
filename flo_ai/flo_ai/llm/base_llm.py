from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from flo_ai.tool.base_tool import Tool
from flo_ai.utils.document_processor import get_default_processor
from flo_ai.utils.logger import logger
from dataclasses import dataclass
from flo_ai.models.document import DocumentMessage


@dataclass
class ImageMessage:
    image_url: Optional[str] = None
    image_bytes: Optional[bytes] = None
    image_file_path: Optional[str] = None
    image_base64: Optional[str] = None
    mime_type: Optional[str] = None


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
    ) -> Dict[str, Any]:
        """Generate a response from the LLM"""
        pass

    async def get_function_call(
        self, response: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        if hasattr(response, 'function_call') and response.function_call:
            return {
                'name': response.function_call.name,
                'arguments': response.function_call.arguments,
            }
        elif isinstance(response, dict) and 'function_call' in response:
            return {
                'name': response['function_call']['name'],
                'arguments': response['function_call']['arguments'],
            }
        return None

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
    def format_image_in_message(self, image: ImageMessage) -> str:
        """Format a image in the message"""
        pass

    async def format_document_in_message(self, document: 'DocumentMessage') -> str:
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
