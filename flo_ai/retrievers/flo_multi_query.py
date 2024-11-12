from typing import List, Union
from langchain_core.vectorstores import VectorStoreRetriever
from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field
from flo_ai.state.flo_session import FloSession
from langchain.retrievers.multi_query import MultiQueryRetriever


class LineList(BaseModel):
    lines: List[str] = Field(description='Lines of text')


class LineListOutputParser(PydanticOutputParser):
    def __init__(self) -> None:
        super().__init__(pydantic_object=LineList)

    def parse(self, text: str) -> LineList:
        lines = text.strip().split('\n')
        return LineList(lines=lines)


class FloMultiQueryRetriever:
    def __init__(self, retriever) -> None:
        self.retriever = retriever


class FloMultiQueryRetriverBuilder:
    def __init__(
        self,
        session: FloSession,
        retriver: VectorStoreRetriever,
        query_prompt: Union[str, None] = None,
    ) -> None:
        self.session = session
        self.retriver = retriver
        self.output_parser = LineListOutputParser()

        self.prompt = PromptTemplate(
            input_variables=['question'],
            template="""You are an AI language model assistant. Your task is to generate three 
            different versions of the given user question to retrieve relevant documents from a vector 
            database. By generating multiple perspectives on the user question, your goal is to help
            the user overcome some of the limitations of the distance-based similarity search. 
            Provide these alternative questions separated by newlines.
            Original question: {question}"""
            if query_prompt is None
            else query_prompt,
        )

    def build(self):
        multi_query_retriever = MultiQueryRetriever.from_llm(
            retriever=self.retriver, llm=self.session.llm, prompt=self.prompt
        )
        return FloMultiQueryRetriever(multi_query_retriever)
