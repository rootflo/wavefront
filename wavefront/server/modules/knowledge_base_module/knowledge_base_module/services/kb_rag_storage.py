from datetime import datetime
import logging
from typing import Any, Dict, List, Tuple

from knowledge_base_module.embeddings.embed import EmbeddingFunc
import tiktoken


class KBRagStorage:
    """Configuration class for EmailRag settings."""

    def __init__(self, embedding_url):
        self.llm_model_name = 'flora-q8'
        self.embedding_model = 'mxbai-embed-large'
        self.embedding_dim = 1024
        self.max_token_size = 8500
        self.tiktoken_model = 'gpt-4o'
        self.chunk_size = 1200
        self.chunk_overlap = 128
        self.embedding = EmbeddingFunc(embedding_url)
        self.logger = logging.getLogger(__name__)

    def encode_string_by_tiktoken(self, content: str, model_name: str = 'gpt-4o'):
        encoder = tiktoken.encoding_for_model(model_name)
        tokens = encoder.encode(content)
        return tokens

    def decode_tokens_by_tiktoken(self, tokens: list[int], model_name: str = 'gpt-4o'):
        decoder = tiktoken.encoding_for_model(model_name)
        content = decoder.decode(tokens)
        return content

    def clean_text(self, content: str) -> str:
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

    def extract_documents(
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
        cleaned_content = [(self.clean_text(content)) for content in results]

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

    def chunk_with_langchain_recursive(
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
            return self._fallback_chunking(
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
            tokens = self.encode_string_by_tiktoken(chunk_text)

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

    def _split_large_chunk(
        self, tokens: List[int], max_tokens: int, overlap: int, model: str
    ) -> List[Dict[str, Any]]:
        """Split a large chunk into smaller pieces."""
        results = []
        for start in range(0, len(tokens), max_tokens - overlap):
            end = min(start + max_tokens, len(tokens))
            chunk_content = self.decode_tokens_by_tiktoken(
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

    def _fallback_chunking(
        self, content: str, max_tokens: int, overlap: int, model: str
    ) -> List[Dict[str, Any]]:
        """Fallback chunking method when LangChain fails."""
        results = []
        tokens = self.encode_string_by_tiktoken(content)
        for index, start in enumerate(range(0, len(tokens), max_tokens - overlap)):
            end = min(start + max_tokens, len(tokens))
            chunk_content = self.decode_tokens_by_tiktoken(
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

    def process_document(self, content: List[str]) -> List[Dict[str, Any]]:
        """
        Process documents and generate embeddings.

        Args:
            content: List of text contents to process

        Returns:
            List of processed documents with embeddings
        """
        all_docs = self.extract_documents(content)
        processed_docs = []
        # for doc in all_docs:
        for doc_id, doc_content in all_docs.items():
            chunks = {
                f'chunk_{ind}': {
                    **data,
                    'full_doc_id': doc_id,
                    'file_path': getattr(doc_content, 'file_path', 'unknown_source'),
                }
                for ind, data in enumerate(
                    self.chunk_with_langchain_recursive(
                        doc_content['content'],
                        self.tiktoken_model,
                        self.chunk_size,
                        self.chunk_overlap,
                    )
                )
            }

            data_list, _ = self.embedding.generate_document_embeddings(
                chunks,
            )

            processed_docs.extend(data_list)

        return processed_docs
