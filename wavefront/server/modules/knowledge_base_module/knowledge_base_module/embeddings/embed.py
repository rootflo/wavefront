import requests
from typing import List
from dataclasses import dataclass


@dataclass
class KnowledgeBaseEmbeddingObject:
    embedding_vector: List[float]
    chunk_text: str
    chunk_index: str


class EmbeddingFunc:
    def __init__(self, embedding_url):
        self.max_batch_size = 32
        self.bgm_url = f'{embedding_url}/v1/embeddings'

    def generate_document_embeddings(self, chunks):
        contents = [v['content'] for v in chunks.values()]
        batches = [
            contents[i : i + self.max_batch_size]
            for i in range(0, len(contents), self.max_batch_size)
        ]

        embeddings = [self.bgm_embedding(batch) for batch in batches]
        # Flatten embeddings list
        flat_embeddings = [item for sublist in embeddings for item in sublist]

        data_list = []
        for i, (k, v) in enumerate(chunks.items()):
            data_list.append(
                KnowledgeBaseEmbeddingObject(
                    embedding_vector=flat_embeddings,
                    chunk_text=v['content'],
                    chunk_index=k,
                )
            )
        return data_list, flat_embeddings

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
