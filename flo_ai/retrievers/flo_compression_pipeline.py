from langchain_core.embeddings import Embeddings
from langchain_text_splitters import CharacterTextSplitter
from langchain_community.document_transformers import EmbeddingsRedundantFilter
from langchain.retrievers.document_compressors import EmbeddingsFilter


class FloCompressionPipeline:
    def __init__(self, embeddings: Embeddings) -> None:
        self.__embeddings = embeddings
        self.__pipeline = []

    def add_chuncking(self, chunk_size=300, chunk_overlap=0):
        splitter = CharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap, separator='. '
        )
        self.__pipeline.append(splitter)

    def add_embedding_reduntant_filter(self):
        redundant_filter = EmbeddingsRedundantFilter(embeddings=self.__embeddings)
        self.__pipeline.append(redundant_filter)

    def add_embedding_relevant_filter(self, threshold: float = 0.50):
        relevant_filter = EmbeddingsFilter(
            embeddings=self.__embeddings, similarity_threshold=threshold
        )
        self.__pipeline.append(relevant_filter)

    def add_flashrank_reranking(self, model_name='ms-marco-MultiBERT-L-12'):
        from langchain.retrievers.document_compressors.flashrank_rerank import (
            FlashrankRerank,
        )

        compressor = FlashrankRerank(model=model_name)
        self.__pipeline.append(compressor)

    def add_cohere_reranking(self, model_name='rerank-english-v3.0'):
        from langchain.retrievers.document_compressors.cohere_rerank import CohereRerank

        compressor = CohereRerank(model=model_name)
        self.__pipeline.append(compressor)

    def get(self):
        return self.__pipeline
