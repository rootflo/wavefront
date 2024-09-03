from langchain_mongodb import MongoDBAtlasVectorSearch
from pymongo import MongoClient
from langchain_openai import OpenAIEmbeddings
import os
from langchain import hub
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
load_dotenv()

from flo_ai import FloSession
from flo_ai.tools.flo_rag_retriver_tool import FloRagRetriverTool

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

import logging

logging.basicConfig()
logging.getLogger("langchain.retrievers.multi_query").setLevel(logging.INFO)

builder = FloRagRetriverTool.Builder(session, store.as_retriever())
builder.enable_multi_query()
tool = builder.build(name="RAGTool", description="RAG to answer question by looking at db")

# rag_tool = rag_builder.with_multi_query().build_rag_tool(name="RAGTool", description="RAG to answer question by looking at db")
print(tool.invoke({"query": "What is the interest rate on housing loans"}))

