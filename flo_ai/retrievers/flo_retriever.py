from langchain_core.vectorstores import VectorStoreRetriever
from langchain_core.runnables import RunnableParallel
from flo_ai.state.flo_session import FloSession
from langchain.schema.output_parser import StrOutputParser
from langchain.schema.runnable import RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from flo_ai.retrievers.flo_multi_query import FloMultiQueryRetriverBuilder
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import DocumentCompressorPipeline
from flo_ai.retrievers.flo_compression_pipeline import FloCompressionPipeline

class FloRagBuilder():
    def __init__(self, session: FloSession, retriever: VectorStoreRetriever) -> None:
        self.session = session
        self.retriever = retriever
        self.default_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", """You are an assistant for question-answering tasks. 
                 Use the following pieces of retrieved context to answer the question. 
                 If you don't know the answer, just say that you don't know. 
                 Use three sentences maximum and keep the answer concise."""),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{question}"),
            ]
        )

    def with_prompt(self, prompt: ChatPromptTemplate):
        self.default_prompt = prompt

    def with_multi_query(self, prompt = None):
        builder = FloMultiQueryRetriverBuilder(session=self.session,
                                                retriver=self.retriever,
                                                  query_prompt=prompt)
        multi_query_retriever = builder.build()
        self.retriever = multi_query_retriever.retriever
        return self
    
    def with_compression(self, pipeline: FloCompressionPipeline):
        pipeline_compressor = DocumentCompressorPipeline(
            transformers=pipeline
        )
        compression_retriever = ContextualCompressionRetriever(
            base_compressor=pipeline_compressor, base_retriever=self.retriever
        )
        self.retriever = compression_retriever
        return self

    def __create_history_aware_retriever(self):
        contextualize_q_system_prompt = """Given a chat history and the latest user question \
        which might reference context in the chat history, formulate a standalone question \
        which can be understood without the chat history. Do NOT answer the question, \
        just reformulate it if needed and otherwise return it as is."""

        contextualize_q_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", contextualize_q_system_prompt),
                MessagesPlaceholder("chat_history"),
                ("human", "{question}"),
            ]
        )
        self.history_aware_retriever = contextualize_q_prompt | self.session.llm | StrOutputParser()
        return self

    def __get_retriever(self):
        def __precontext_retriver(input_prompt: dict):
            if input_prompt.get("chat_history"):
                return self.history_aware_retriever
            else:
                return input_prompt["question"]
        return __precontext_retriver | self.retriever
    
    def __format_docs(self, docs):
        return "\n\n".join(doc.page_content for doc in docs)
    
    def __get_optional_chat_history(self, x):
        return x["chat_history"] if "chat_history" in x else []
    
    def __build_history_aware_rag(self):
        self.history_aware_retriever = self.__create_history_aware_retriever()
        rag_chain = (
            RunnablePassthrough.assign(
                context=(lambda x: x["context"]),
            )
            | self.default_prompt
            | self.session.llm   
        )

        rag_chain_with_source = RunnableParallel(
            {
                "context": self.__get_retriever() | self.__format_docs,
                "question": RunnablePassthrough(),
                "chat_history": lambda x: self.__get_optional_chat_history(x)
            }
        ).assign(answer=rag_chain)
        return rag_chain_with_source

    def build(self):
        return self.__build_history_aware_rag()
