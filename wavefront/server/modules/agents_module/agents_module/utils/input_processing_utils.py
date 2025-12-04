"""
Utility functions for processing inference inputs
"""

import re
from typing import Any, List, Union
from fastapi import HTTPException, status
from flo_ai import (
    AssistantMessage,
    TextMessageContent,
    ImageMessageContent,
    DocumentMessageContent,
    UserMessage,
)
from common_module.log.logger import logger


def process_inference_inputs(
    inputs: Union[List[dict | str], str],
) -> Union[UserMessage, List[Union[UserMessage, AssistantMessage]]]:
    """
    Process inputs for inference, handling both string and list inputs with ImageMessage processing

    Args:
        inputs: Input data - can be a string or list containing strings and ImageMessage objects

    Returns:
        Union[str, List]: Processed inputs ready for inference

    Raises:
        HTTPException: 400 Bad Request if base64 image data is invalid
    """
    # Process inputs based on type
    if isinstance(inputs, str):
        return UserMessage(content=inputs)
    else:
        resolved_inputs = []
        for input_item in inputs:
            if input_item.get('role') == 'assistant':
                resolved_inputs.append(
                    AssistantMessage(content=input_item.get('content'))
                )
            elif input_item.get('role') == 'user':
                input_content = input_item.get('content', {})
                if is_image_message(input_content):
                    # Extract image_bytes and mime_type from image_base64
                    try:
                        data_url_pattern = r'^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$'
                        match = re.match(
                            data_url_pattern, input_content.get('image_base64')
                        )
                        if match:
                            mime_type = match.group(1)
                            processed_image = UserMessage(
                                content=ImageMessageContent(
                                    base64=match.group(2), mime_type=mime_type
                                )
                            )
                            resolved_inputs.append(processed_image)
                        else:
                            resolved_inputs.append(
                                UserMessage(
                                    content=ImageMessageContent(
                                        base64=input_content.get('image_base64'),
                                        mime_type=input_content.get('mime_type'),
                                    ),
                                )
                            )
                    except Exception as e:
                        logger.error(
                            f'Error processing ImageMessage base64: {e}, message: {input_item}'
                        )
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f'Invalid base64 image data: {e}',
                        )
                elif is_doc_message(input_content):
                    # DocumentMessage - append directly
                    resolved_inputs.append(
                        UserMessage(
                            content=DocumentMessageContent(
                                base64=input_content.get('document_base64'),
                                mime_type=input_content.get('mime_type'),
                            )
                        )
                    )
                elif is_text_message(input_content):
                    resolved_inputs.append(
                        UserMessage(
                            content=TextMessageContent(text=input_item.get('content'))
                        )
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f'Invalid input: {input_item}',
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f'Invalid input: {input_item}',
                )

    return resolved_inputs


def is_image_message(input_item: dict) -> bool:
    """
    Check if the input item is an instance of ImageMessage

    Args:
        input_item: Input item to check
    Returns:
        bool: True if input_item is an ImageMessage, False otherwise

    """
    return (
        'image_url' in input_item
        or 'image_base64' in input_item
        or 'image_bytes' in input_item
        or 'image_file_path' in input_item
    )


def is_doc_message(input_item: dict) -> bool:
    """
    Check if the input item is an instance of DocumentMessage

    Args:
        input_item: Input item to check
    Returns:
        bool: True if input_item is a DocumentMessage, False otherwise
    """
    return (
        'document_url' in input_item
        or 'document_base64' in input_item
        or 'document_bytes' in input_item
        or 'document_file_path' in input_item
    )


def is_text_message(input_item: Any) -> bool:
    """
    Check if the input item is an instance of TextMessage

    Args:
        input_item: Input item to check
    Returns:
        bool: True if input_item is a TextMessage, False otherwise
    """
    return isinstance(input_item, str)
