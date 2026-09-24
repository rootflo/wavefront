"""
Utility functions for processing inference inputs
"""

import asyncio
import base64
import binascii
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
from agents_module.utils.document_text_extraction import (
    EXTRACTABLE_DOCUMENT_MIME_TYPES,
    DocumentExtractionError,
    extract_document_text,
)
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
                    raw_image = input_content.get('image_base64')

                    # Anything that is not a string cannot be parsed or
                    # forwarded. Caught here so it keeps its own error rather
                    # than reaching the mime gate as an unresolvable type.
                    if not isinstance(raw_image, str):
                        logger.error(
                            f'Error processing ImageMessage base64 at input index '
                            f'{index}: expected a string, '
                            f'got {type(raw_image).__name__}'
                        )
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=(
                                'Invalid base64 image data: expected a string, '
                                f'got {type(raw_image).__name__}'
                            ),
                        )

                    # The shared helper, so this resolves a data URL exactly as
                    # validate_inference_inputs_media does for the async
                    # endpoints — same handling of parameters before `;base64`,
                    # of casing, and of a non-image mime declared on an image
                    # field. A local regex here had diverged on all three.
                    data_url_mime, stripped_image = split_data_url(raw_image)
                    if stripped_image is not None:
                        image_base64 = stripped_image
                        image_mime_type = data_url_mime
                    else:
                        image_base64 = raw_image
                        image_mime_type = input_content.get('mime_type')

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

                    # Office and CSV files are converted to text here rather
                    # than forwarded as a document block: no provider this
                    # deployment targets can parse them. `document_mime_type` is
                    # None for an unresolvable mime, which means "assume PDF" --
                    # the `in` test keeps that case on the native path.
                    if document_mime_type in EXTRACTABLE_DOCUMENT_MIME_TYPES:
                        document_content = TextMessageContent(
                            text=_extract_document_to_text(
                                base64_value=document_base64,
                                mime_type=document_mime_type,
                                file_name=input_content.get('file_name'),
                                url=input_content.get('document_url'),
                                index=index,
                            )
                        )
                    else:
                        document_content = DocumentMessageContent(
                            base64=document_base64,
                            mime_type=document_mime_type,
                            url=input_content.get('document_url'),
                            file_name=input_content.get('file_name'),
                        )

                    resolved_inputs.append(UserMessage(content=document_content))
                elif is_text_message(input_content):
                    resolved_inputs.append(
                        UserMessage(
                            content=TextMessageContent(text=input_item.get('content'))
                        )
                    )
                else:
                    # The item itself is deliberately not echoed: on the media
                    # branches it carries the base64 payload, so reflecting it
                    # sends a multi-megabyte body back for a 400. The index
                    # locates it for the caller.
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f'Invalid input at index {index}: content must be a '
                            'string, an image or a document'
                        ),
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f'Invalid input at index {index}: role must be '
                        "'user' or 'assistant'"
                    ),
                )

    return resolved_inputs


async def process_inference_inputs_async(
    inputs: Union[List[dict | str], str],
) -> Union[UserMessage, List[Union[UserMessage, AssistantMessage]]]:
    """`process_inference_inputs`, run off the event loop, for request handlers.

    Office documents are decoded and parsed during processing -- a DOCX/XLSX
    parse, or an antiword subprocess allowed up to its 30 second timeout -- and
    on an async route that stalls every other request the worker is serving.

    The background workers call the sync version directly: the Celery worker
    runs one task at a time under the solo pool, and each workflow_job thread
    handles its messages one after another, so neither has concurrent work on
    its loop to protect.
    """
    return await asyncio.to_thread(process_inference_inputs, inputs)


def _extract_document_to_text(
    base64_value: Any,
    mime_type: str,
    file_name: Any,
    url: Any,
    index: int,
) -> str:
    """Decode and extract an Office/CSV document, as a 400 on any failure.

    Separated from the loop only to keep the three failure modes — no bytes, bad
    base64, unreadable document — from burying the branch they belong to.
    """
    if not isinstance(base64_value, str) or not base64_value:
        # A URL is the realistic way to get here: the schema accepts
        # `document_url`, but nothing server-side fetches remote documents, and
        # flo_ai's default formatter refuses them too. Failing here beats
        # handing the model an empty text block.
        detail = (
            f'Document at index {index} has no inline content. '
            f'Send `document_base64`; `document_url` is not supported for '
            f'`{mime_type}` files.'
            if url
            else f'Document at index {index} has no `document_base64` content.'
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    try:
        data = base64.b64decode(base64_value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Invalid base64 document data at index {index}: {exc}',
        ) from exc

    try:
        return extract_document_text(
            data, mime_type, file_name if isinstance(file_name, str) else None
        )
    except DocumentExtractionError as exc:
        logger.error(f'Document extraction failed at input index {index}: {exc}')
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Could not read the document at index {index}. {exc}',
        ) from exc


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
