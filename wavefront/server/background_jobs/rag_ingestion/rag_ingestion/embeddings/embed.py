from rag_ingestion.models.knowledge_base_embeddings import KnowledgeBaseEmbeddingObject
import requests
from rag_ingestion.env import INFERENCE_SERVICE_URL
from flo_utils.utils.log import logger


class EmbeddingFunc:
    def __init__(self):
        self.max_batch_size = 32
        self.bgm_url = f'{INFERENCE_SERVICE_URL}'
        logger.info(f'The embedding url is {INFERENCE_SERVICE_URL}')

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
                'input': texts,
                'encoding_format': 'float',
            },
            timeout=60,
        )
        response.raise_for_status()
        res = response.json()
        return res['data'][0]['embedding']
