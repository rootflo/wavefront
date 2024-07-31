from langchain_mongodb import MongoDBAtlasVectorSearch
from pymongo import MongoClient
from langchain_openai import OpenAIEmbeddings
import os
from langchain import hub
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from dotenv import load_dotenv
load_dotenv()

from flo_ai import FloSession
from flo_ai.retrievers.flo_retriever import FloRagBuilder

db_url = os.getenv("MONGO_DB_URL")

connection_timeout = 60000
mongo_client = MongoClient(db_url, connectTimeoutMS=connection_timeout, socketTimeoutMS=connection_timeout)
mongo_embedding_collection = (mongo_client
                        .get_database("dohabank")
                        .get_collection("products"))

store = MongoDBAtlasVectorSearch(
    collection=mongo_embedding_collection,
    embedding_key="embedding",
    embedding=OpenAIEmbeddings(model="text-embedding-3-small"),
    index_name="bank-products-index",
)


llm = ChatOpenAI(temperature=0, model_name='gpt-4o')
session = FloSession(llm)
rag_builder = FloRagBuilder(session, store.as_retriever())

import logging

logging.basicConfig()
logging.getLogger("langchain.retrievers.multi_query").setLevel(logging.INFO)

rag = rag_builder.with_multi_query().build()
print(rag.invoke({ "question": "Tell me about corporate loans" }))

