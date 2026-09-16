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
from agents_module.utils.mime_type_utils import (
    ensure_supported_document_mime_type,
    ensure_supported_image_mime_type,
    split_data_url,
)


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
        for index, input_item in enumerate(inputs):
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
                            image_base64 = match.group(2)
                            image_mime_type = match.group(1)
                        else:
                            image_base64 = input_content.get('image_base64')
                            image_mime_type = input_content.get('mime_type')
                    except Exception as e:
                        logger.error(
                            f'Error processing ImageMessage base64: {e}, message: {input_item}'
                        )
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f'Invalid base64 image data: {e}',
                        )

                    # Gated outside the try on purpose: an unsupported-type
                    # rejection must not be swallowed by the except above and
                    # relabelled as a base64 error.
                    image_mime_type = ensure_supported_image_mime_type(
                        mime_type=image_mime_type,
                        file_name=input_content.get('file_name'),
                        index=index,
                    )

                    resolved_inputs.append(
                        UserMessage(
                            content=ImageMessageContent(
                                base64=image_base64,
                                mime_type=image_mime_type,
                                file_name=input_content.get('file_name'),
                            ),
                        )
                    )
                elif is_doc_message(input_content):
                    raw_document = input_content.get('document_base64')

                    document_mime_type = ensure_supported_document_mime_type(
                        mime_type=input_content.get('mime_type'),
                        base64_value=raw_document,
                        file_name=input_content.get('file_name'),
                        url=input_content.get('document_url'),
                        index=index,
                    )

                    # Documents arrive as a `data:` URL just as often as images
                    # do. The prefix has to come off here: every provider feeds
                    # `.base64` straight to a decoder, and `data:...` decodes to
                    # garbage rather than failing loudly.
                    _, stripped_document = split_data_url(raw_document)
                    document_base64 = (
                        stripped_document
                        if stripped_document is not None
                        else raw_document
                    )

                    resolved_inputs.append(
                        UserMessage(
                            content=DocumentMessageContent(
                                base64=document_base64,
                                mime_type=document_mime_type,
                                url=input_content.get('document_url'),
                                file_name=input_content.get('file_name'),
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


def validate_inference_inputs_media(
    inputs: Union[List[dict | str], str],
) -> None:
    """Gate the mime types of an inference request's media inputs.

    For the synchronous endpoints `process_inference_inputs` already gates as
    it builds the messages. The async endpoints enqueue the raw payload and
    only resolve it inside the worker, so without this the caller would get a
    202 and discover the unsupported file as a failed execution later — after
    the bytes had already been uploaded to cloud storage. Call this before
    enqueueing.

    Args:
        inputs: The raw `inputs` field from the request body

    Raises:
        HTTPException: 400 Bad Request if a media input's mime type is not
            supported
    """
    if isinstance(inputs, str):
        return

    for index, input_item in enumerate(inputs):
        if not isinstance(input_item, dict):
            continue
        if input_item.get('role') == 'assistant':
            continue

        input_content = input_item.get('content')
        if not isinstance(input_content, dict):
            continue

        if is_image_message(input_content):
            ensure_supported_image_mime_type(
                mime_type=input_content.get('mime_type'),
                base64_value=input_content.get('image_base64'),
                file_name=input_content.get('file_name'),
                url=input_content.get('image_url'),
                index=index,
            )
        elif is_doc_message(input_content):
            ensure_supported_document_mime_type(
                mime_type=input_content.get('mime_type'),
                base64_value=input_content.get('document_base64'),
                file_name=input_content.get('file_name'),
                url=input_content.get('document_url'),
                index=index,
            )


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
