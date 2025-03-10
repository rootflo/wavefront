from langchain_core.vectorstores import VectorStoreRetriever
from langchain_core.runnables import RunnableParallel, Runnable
from flo_ai.state.flo_session import FloSession
from langchain.schema.output_parser import StrOutputParser
from langchain.schema.runnable import RunnablePassthrough
from flo_ai.retrievers.flo_multi_query import FloMultiQueryRetriverBuilder
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import DocumentCompressorPipeline
from flo_ai.retrievers.flo_compression_pipeline import FloCompressionPipeline
from functools import partial
from pydantic import BaseModel, Field
from langchain_core.tools import Tool
from typing import Optional
from langchain_core.callbacks import Callbacks
from langchain_core.prompts import (
    BasePromptTemplate,
    PromptTemplate,
    aformat_document,
    format_document,
    ChatPromptTemplate,
    MessagesPlaceholder,
)
from typing import List


class FloRagBaseMessage(BaseModel):
    content: str


class FloRagToolInput(BaseModel):
    messages: List[FloRagBaseMessage] = Field(
        description='query to look up in the vector store'
    )


def _get_relevant_documents(
    messages: List[FloRagBaseMessage],
    retriever: VectorStoreRetriever,
    document_prompt: BasePromptTemplate,
    document_separator: str,
    callbacks: Callbacks = None,
) -> str:
    docs = retriever.invoke(messages[-1].content, config={'callbacks': callbacks})
    return document_separator.join(
        format_document(doc, document_prompt) for doc in docs
    )


async def _aget_relevant_documents(
    messages: List[str],
    retriever: VectorStoreRetriever,
    document_prompt: BasePromptTemplate,
    document_separator: str,
    callbacks: Callbacks = None,
) -> str:
    docs = await retriever.ainvoke(
        messages[-1].content, config={'callbacks': callbacks}
    )
    return document_separator.join(
        [await aformat_document(doc, document_prompt) for doc in docs]
    )


class FloRagBuilder:
    def __init__(self, session: FloSession, retriever: VectorStoreRetriever) -> None:
        self.session = session
        self.retriever = retriever
        self.default_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    'system',
                    """You are an assistant for question-answering tasks. 
                 Use the following pieces of retrieved context to answer the question. 
                 If you don't know the answer, just say that you don't know. 
                 Use three sentences maximum and keep the answer concise.

                 Here is the context:
                 {context}
                 
                 """,
                ),
                MessagesPlaceholder(variable_name='chat_history'),
                ('human', '{question}'),
            ]
        )
        self.history_aware_retriever = self.__create_history_aware_retriever()

    def with_prompt(self, prompt: ChatPromptTemplate):
        self.default_prompt = prompt
        return self

    def with_multi_query(self, prompt=None):
        builder = FloMultiQueryRetriverBuilder(
            session=self.session, retriver=self.retriever, query_prompt=prompt
        )
        multi_query_retriever = builder.build()
        self.retriever = multi_query_retriever.retriever
        return self

    def with_compression(self, pipeline: FloCompressionPipeline):
        pipeline_compressor = DocumentCompressorPipeline(transformers=pipeline.get())
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
                ('system', contextualize_q_system_prompt),
                MessagesPlaceholder('chat_history'),
                ('human', '{question}'),
            ]
        )
        self.history_aware_retriever = (
            contextualize_q_prompt | self.session.llm | StrOutputParser()
        )
        return self.history_aware_retriever

    def __get_retriever(self):
        def __precontext_retriver(input_prompt: dict):
            if input_prompt.get('chat_history'):
                return self.history_aware_retriever
            else:
                return input_prompt['question']

        return __precontext_retriver | self.retriever

    def __format_docs(self, docs):
        return '\n\n'.join(doc.page_content for doc in docs)

    def __get_optional_chat_history(self, x):
        return x['chat_history'] if 'chat_history' in x else []

    def __build_history_aware_rag(self):
        rag_chain = (
            RunnablePassthrough.assign(
                context=(lambda x: x['context']),
            )
            | self.default_prompt
            | self.session.llm
        )

        rag_chain_with_source = RunnableParallel(
            {
                'context': self.__get_retriever() | self.__format_docs,
                'question': RunnablePassthrough(),
                'chat_history': lambda x: self.__get_optional_chat_history(x),
            }
        ).assign(answer=rag_chain)
        return rag_chain_with_source

    def build_rag(self):
        return self.__build_history_aware_rag()

    def build_retriever_tool(self, name, description):
        return self.__create_retriever_tool(self.retriever, name, description)

    @staticmethod
    def __get_rag_answer(messages: List[FloRagBaseMessage], runnable: Runnable):
        question = messages[-1].content
        chat_history = messages[:-1]
        result = runnable.invoke({'question': question, 'chat_history': chat_history})
        return result['answer'].content

    @staticmethod
    async def __aget_rag_answer(messages: List[FloRagBaseMessage], runnable: Runnable):
        question = messages[-1].content
        chat_history = messages[:-1]
        result = await runnable.ainvoke(
            {'question': question, 'chat_history': chat_history}
        )
        return result['answer'].content

    def __create_retriever_tool(
        self,
        retriever: VectorStoreRetriever,
        name: str,
        description: str,
        *,
        document_prompt: Optional[BasePromptTemplate] = None,
        document_separator: str = '\n',
    ) -> Tool:
        document_prompt = document_prompt or PromptTemplate.from_template(
            '{page_content}'
        )
        func = partial(
            _get_relevant_documents,
            retriever=retriever,
            document_prompt=document_prompt,
            document_separator=document_separator,
        )
        afunc = partial(
            _aget_relevant_documents,
            retriever=retriever,
            document_prompt=document_prompt,
            document_separator=document_separator,
        )
        return Tool(
            name=name,
            description=description,
            func=func,
            coroutine=afunc,
            args_schema=FloRagToolInput,
        )

    @staticmethod
    def __create_rag_tool(runnable_rag: Runnable, name: str, description: str) -> Tool:
        func = partial(FloRagBuilder.__get_rag_answer, runnable=runnable_rag)

        afunc = partial(FloRagBuilder.__aget_rag_answer, runnable=runnable_rag)

        return Tool(
            name=name,
            description=description,
            func=func,
            coroutine=afunc,
            args_schema=FloRagToolInput,
        )

    def build_rag_tool(self, name, description) -> Tool:
        rag = self.__build_history_aware_rag()
        return FloRagBuilder.__create_rag_tool(rag, name, description)
