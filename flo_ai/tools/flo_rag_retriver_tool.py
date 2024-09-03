from langchain.tools import Tool
from langchain_core.runnables import Runnable
from flo_ai.retrievers.flo_retriever import FloRagBuilder
from flo_ai.state.flo_session import FloSession
from flo_ai.retrievers.flo_compression_pipeline import FloCompressionPipeline
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.vectorstores import VectorStoreRetriever

class FloRagRetrieverTool():

    def __init__(self) -> None:
        raise ValueError("You are supposed to use Builder, FloRagRetriverTool.Builder()")

    class Builder():

        def __init__(self, 
                     session: FloSession,
                     retriever: VectorStoreRetriever) -> None:
            self.session = session
            self.retriver = retriever
            self.multiquery = False
            self.custom_prompt: ChatPromptTemplate = None
            self.extraction_pipeline: FloCompressionPipeline = None 

        def add_custom_prompt(self, custom_prompt: ChatPromptTemplate):
            self.custom_prompt = custom_prompt

        def add_custom_system_prompt(self, custom_system_prompt: str):
            system_prompt = custom_system_prompt if custom_system_prompt is not None else """You are an assistant for question-answering tasks. 
                 Use the following pieces of retrieved context to answer the question. 
                 If you don't know the answer, just say that you don't know. 
                 Use three sentences maximum and keep the answer concise."""
            self.custom_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    MessagesPlaceholder(variable_name="chat_history"),
                    ("human", "{question}"),
                ]
            )

        def add_extraction_pipeline(self, pipeline: FloCompressionPipeline):
            self.extraction_pipeline = pipeline 

        def enable_multi_query(self):
            self.multiquery = True

        def build(self, name: str, description: str) -> Tool:
            rag_builder = FloRagBuilder(self.session, self.retriver)
            if self.custom_prompt is not None:
                rag_builder.with_prompt(self.custom_prompt)
            if self.multiquery:
                rag_builder.with_multi_query()
            if self.extraction_pipeline is not None:
                rag_builder.with_compression(self.extraction_pipeline)
            return rag_builder.build_rag_tool(name=name, description=description)

            
