from rag_ingestion.models.knowledge_base_embeddings import KnowledgeBaseEmbeddingObject
import requests
from rag_ingestion.env import EMBEDDING_SERVICE_URL
from flo_utils.utils.log import logger


class EmbeddingFunc:
    def __init__(self):
        self.max_batch_size = 32
        self.bgm_url = f'{EMBEDDING_SERVICE_URL}/v1/embeddings'
        logger.info(f'The embedding url is {EMBEDDING_SERVICE_URL}')

    def generate_document_embeddings(self, chunks):
        contents = [v['content'] for v in chunks.values()]
        batches = [
            contents[i : i + self.max_batch_size]
            for i in range(0, len(contents), self.max_batch_size)
        ]
        embeddings = [self.bgm_embedding(batch) for batch in batches[0]]
        data_list = []
        for i, (k, v) in enumerate(chunks.items()):
            data_list.append(
                KnowledgeBaseEmbeddingObject(
                    embedding_vector=embeddings[i],
                    chunk_text=v['content'],
                    chunk_index=k,
                )
            )
        return data_list, embeddings

    def generate_chunk_embeddings(self, chunks):
        embeddings = [self.bgm_embedding(chunks)]
        return embeddings

    def bgm_embedding(self, texts):
        response = requests.post(
            self.bgm_url,
            json={
                'model': 'BAAI/bge-m3',
                'input': texts,
                'encoding_format': 'float',
            },
        )
        return response.json()['data'][0]['embedding']
