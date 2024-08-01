import os
from langchain_mongodb import MongoDBAtlasVectorSearch
from pymongo import MongoClient
from langchain_openai import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
load_dotenv()

from flo_ai import FloSession
from flo_ai.retrievers.flo_retriever import FloRagBuilder
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from flo_ai.retrievers.flo_compression_pipeline import FloCompressionPipeline

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

custom_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", """You are an assistant for banking employees, of Doha Bank.
                 Use the following pieces of retrieved context to answer the question. 
                 If you don't know the answer, just say that you don't know. 
                 Try to answer questions as bullet points that are easy to read"""),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{question}"),
            ]
        )

compression_pipeline = FloCompressionPipeline(OpenAIEmbeddings(model="text-embedding-3-small"))
compression_pipeline.add_embedding_reduntant_filter()
compression_pipeline.add_embedding_relevant_filter()

rag = rag_builder.with_prompt(custom_prompt).with_multi_query().with_compression(compression_pipeline).build_rag()
print(rag.invoke({ "question": "What are the documents applying for housing loan" }))

