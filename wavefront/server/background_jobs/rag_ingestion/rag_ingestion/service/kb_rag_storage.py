import logging
import tiktoken
import uuid
import httpx
import time
import ast
import numpy as np
from flo_utils.utils.log import logger
from datetime import datetime
from dataclasses import dataclass
from rag_ingestion.env import FLOWARE_SERVICE_URL, APP_ENV, PASSTHROUGH_SECRET
from rag_ingestion.constants.auth import RootfloHeaders
from rag_ingestion.models.knowledge_base_embeddings import (
    KnowledgeBaseEmbeddingObject,
    RetrieveParams,
)
from typing import Any, List, Dict, Tuple, Optional
from rag_ingestion.embeddings.embed import EmbeddingFunc
from rag_ingestion.processors.file_processor import DocumentType


@dataclass
class EmbeddingsToStore:
    kb_embeddings: List[KnowledgeBaseEmbeddingObject]
    doc_id: str
    kb_id: str
    file_type: DocumentType


class KBRagStorage:
    """Configuration class for EmailRag settings."""

    def __init__(self):
        self.llm_model_name = 'flora-q8'
        self.embedding_model = 'mxbai-embed-large'
        self.embedding_dim = 1024
        self.max_token_size = 8500
        self.tiktoken_model = 'gpt-4o'
        self.chunk_size = 1200
        self.chunk_overlap = 128
        self.embedding = EmbeddingFunc()
        self.logger = logging.getLogger(__name__)
        self.app_env = APP_ENV
        self.passthrough_secret = PASSTHROUGH_SECRET

    def _fetch_headers(self) -> dict:
        """
        Fetch headers for HTTP requests to floware service.
        Adds passthrough authentication header for non-production environments.

        Returns:
            dict: Headers to include in HTTP requests
        """
        headers = {'Content-Type': 'application/json'}

        # Add passthrough header for non-production environments
        if self.app_env != 'production' and self.passthrough_secret:
            headers[RootfloHeaders.PASSTHROUGH] = self.passthrough_secret

        return headers

    def __encode_string_by_tiktoken(self, content: str, model_name: str = 'gpt-4o'):
        encoder = tiktoken.encoding_for_model(model_name)
        tokens = encoder.encode(content)
        return tokens

    def __decode_tokens_by_tiktoken(
        self, tokens: list[int], model_name: str = 'gpt-4o'
    ):
        decoder = tiktoken.encoding_for_model(model_name)
        content = decoder.decode(tokens)
        return content

    def __clean_text(self, content: str) -> str:
        """
        Clean and normalize text content from documents.

        Args:
            content: The raw text content to clean

        Returns:
            Cleaned and normalized text
        """
        if not content or not isinstance(content, str):
            return ''

        # Basic cleaning
        content = content.replace('\x00', '')  # Remove null bytes
        return content

    def __extract_documents(
        self, contents: List[str]
    ) -> List[List[Tuple[str, Dict[str, Any]]]]:
        """
        Extract content from files with improved error handling and parallel processing.

        Args:
            contents: List of text contents to process

        Returns:
            List of document tuples containing (doc_id, doc_content)
        """
        if not contents:
            self.logger.warning('No contents provided for extraction')
            return []

        # Process contents
        results = []
        for content in contents:
            processed_content = content
            if processed_content:
                results.append(processed_content)

        if not results:
            return []

        # Clean and process results
        cleaned_content = [(self.__clean_text(content)) for content in results]

        # Create document structure
        docs = {
            f'doc_{index}': {
                'content': content,
                'content_length': len(content),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
            }
            for index, (content) in enumerate(cleaned_content)
        }

        return docs

    def __chunk_with_langchain_recursive(
        self,
        content: str,
        tiktoken_model: str,
        chunk_size: int,
        chunk_overlap: int,
        separators: List[str] = ['\n\n', '\n', ' ', ''],
    ) -> List[Dict[str, Any]]:
        """
        Chunk content using LangChain's RecursiveCharacterTextSplitter.

        Args:
            content: The text content to chunk
            tiktoken_model: The tiktoken model to use
            chunk_size: Approximate chunk size in characters
            chunk_overlap: Character overlap between chunks
            separators: List of separators for recursive splitting

        Returns:
            List of chunks with token counts and content
        """
        try:
            return self.__chunk_with_custom_splitter(
                content,
                self.max_token_size,
                self.chunk_overlap,
                tiktoken_model,
                chunk_size,
                chunk_overlap,
                separators,
            )
        except Exception as e:
            self.logger.error(
                f'Error using LangChain RecursiveCharacterTextSplitter: {e}'
            )
            return self.__fallback_chunking(
                content, self.max_token_size, self.chunk_overlap, tiktoken_model
            )

    def __chunk_with_custom_splitter(
        self,
        content: str,
        max_token_size: int,
        overlap_token_size: int,
        tiktoken_model: str,
        chunk_size: int,
        chunk_overlap: int,
        separators: List[str],
    ) -> List[Dict[str, Any]]:
        """Handle chunking using custom recursive text splitter."""
        results = []

        # Default separators if none provided
        if not separators:
            separators = ['\n\n', '\n', ' ', '']

        def recursive_split(text: str, seps: List[str]) -> List[str]:
            if not seps or len(text) <= chunk_size:
                return [text] if text.strip() else []

            sep = seps[0]
            splits = text.split(sep) if sep else list(text)

            # Keep separator with text
            if sep:
                splits = [splits[0]] + [sep + s for s in splits[1:] if s]

            chunks = []
            current = ''

            for split in splits:
                if len(split) > chunk_size:
                    # Add current chunk if exists
                    if current:
                        chunks.append(current)
                        # Add overlap
                        if chunk_overlap > 0:
                            current = (
                                current[-chunk_overlap:]
                                if len(current) > chunk_overlap
                                else ''
                            )
                        else:
                            current = ''

                    # Recursively split large piece
                    chunks.extend(recursive_split(split, seps[1:]))

                elif len(current) + len(split) <= chunk_size:
                    current += split
                else:
                    # Start new chunk
                    if current:
                        chunks.append(current)
                        # Add overlap
                        if chunk_overlap > 0 and len(current) > chunk_overlap:
                            current = current[-chunk_overlap:] + split
                        else:
                            current = split
                    else:
                        current = split

            if current:
                chunks.append(current)

            return [c for c in chunks if c.strip()]

        # Split content into chunks
        chunks = recursive_split(content, separators)
        # Process each chunk
        for chunk_index, chunk_text in enumerate(chunks):
            tokens = self.__encode_string_by_tiktoken(chunk_text)

            if len(tokens) > max_token_size:
                results.extend(
                    self.__split_large_chunk(
                        tokens, max_token_size, overlap_token_size, tiktoken_model
                    )
                )
            else:
                results.append(
                    {
                        'tokens': len(tokens),
                        'content': chunk_text.strip(),
                        'chunk_order_index': len(results),
                        'chunk_index': chunk_index,
                        'metadata': {'start_index': content.find(chunk_text)},
                    }
                )

        return results

    def __split_large_chunk(
        self, tokens: List[int], max_tokens: int, overlap: int, model: str
    ) -> List[Dict[str, Any]]:
        """Split a large chunk into smaller pieces."""
        results = []
        for start in range(0, len(tokens), max_tokens - overlap):
            end = min(start + max_tokens, len(tokens))
            chunk_content = self.__decode_tokens_by_tiktoken(
                tokens[start:end],
                model_name=model,
            )
            results.append(
                {
                    'tokens': end - start,
                    'content': chunk_content.strip(),
                    'chunk_order_index': len(results),
                }
            )
        return results

    def __fallback_chunking(
        self, content: str, max_tokens: int, overlap: int, model: str
    ) -> List[Dict[str, Any]]:
        """Fallback chunking method when LangChain fails."""
        results = []
        tokens = self.__encode_string_by_tiktoken(content)
        for index, start in enumerate(range(0, len(tokens), max_tokens - overlap)):
            end = min(start + max_tokens, len(tokens))
            chunk_content = self.__decode_tokens_by_tiktoken(
                tokens[start:end], model_name=model
            )
            results.append(
                {
                    'tokens': end - start,
                    'content': chunk_content.strip(),
                    'chunk_order_index': index,
                }
            )
        return results

    def process_document(
        self, content: List[str]
    ) -> List[KnowledgeBaseEmbeddingObject]:
        """
        Process documents and generate embeddings.

        Args:
            content: List of text contents to process

        Returns:
            List of processed documents with embeddings
        """
        all_docs = self.__extract_documents(content)
        processed_docs = []
        for doc_id, doc_content in all_docs.items():
            chunks = {
                f'chunk_{ind}': {
                    **data,
                    'full_doc_id': doc_id,
                    'file_path': getattr(doc_content, 'file_path', 'unknown_source'),
                }
                for ind, data in enumerate(
                    self.__chunk_with_langchain_recursive(
                        doc_content['content'],
                        self.tiktoken_model,
                        self.chunk_size,
                        self.chunk_overlap,
                    )
                )
            }

            data_list, _ = self.embedding.generate_document_embeddings(chunks)
            processed_docs.extend(data_list)

        return processed_docs

    def retrieve_documents(
        self,
        query: str,
        kb_id: uuid.UUID,
        threshold: Optional[float] = None,
        top_k: Optional[int] = None,
        vector_weight: Optional[float] = None,
        keyword_weight: Optional[float] = None,
    ) -> list:
        """
        Retrieve documents for a specific knowledge base
        Args:
            query: Text query for search
            kb_id: Knowledge base ID to filter results
            threshold: Cosine similarity threshold (default: 0.2)
            top_k: Number of results to return (default: 5)
            vector_weight: Weight for vector similarity score (default: 0.7)
            keyword_weight: Weight for keyword similarity score (default: 0.3)
        Returns:
            List of retrieved documents
        """
        if not isinstance(query, str):
            raise ValueError('Query must be in string format')

        query_embeddings = self.embedding.generate_chunk_embeddings([query])
        query_embeddings = np.array(query_embeddings, dtype=np.float16).tolist()
        query_embeddings = ast.literal_eval(','.join(map(str, query_embeddings[0])))

        params = RetrieveParams(
            kb_id=str(kb_id),
            threshold=threshold,
            top_k=top_k,
            vector_weight=vector_weight,
            keyword_weight=keyword_weight,
        )
        reranked_docs = self.retrieve_docs_with_retry(query, query_embeddings, params)
        return reranked_docs

    def upload_embedding_with_retry(
        self,
        embeddings: List[EmbeddingsToStore],
        max_retries=3,
        initial_delay=1.0,
    ):
        """
        Upload a single embedding with exponential backoff retry logic.
        """
        doc_wise_embeddings = []
        for embedding_obj in embeddings:
            data = embedding_obj.kb_embeddings
            payload = {
                'embedding_vector': [
                    embedding_obj.embedding_vector for embedding_obj in data
                ],
                'embedding_vector_1': [
                    embedding_obj.embedding_vector_1 for embedding_obj in data
                ],
                'document_id': embedding_obj.doc_id,
                'kb_id': embedding_obj.kb_id,
                'chunk_text': [embedding_obj.chunk_text for embedding_obj in data],
                'chunk_index': [embedding_obj.chunk_index for embedding_obj in data],
            }
            doc_wise_embeddings.append(payload)
        return self._upload_doc_wise_embeddings(
            doc_wise_embeddings, max_retries, initial_delay
        )

    def _upload_doc_wise_embeddings(
        self,
        doc_wise_embeddings: List[Dict[str, Any]],
        max_retries=3,
        initial_delay=1.0,
    ):
        url = f'{FLOWARE_SERVICE_URL}/floware/v1/store_embedding'
        delay = initial_delay
        for attempt in range(max_retries):
            try:
                response = httpx.post(
                    url,
                    json={'embeddings': doc_wise_embeddings},
                    headers=self._fetch_headers(),
                )
                if response.status_code == 200:
                    return response
                else:
                    logger.info(f'The error request was {response.text}')
            except Exception as e:
                logger.error(f'The error while uploading doc wise embeddings was {e}')
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 1.5
        raise Exception('Failed to upload doc wise embeddings after max retries')
