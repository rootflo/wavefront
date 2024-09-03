from langchain.tools import Tool
from langchain_core.runnables import Runnable
from flo_ai.retrievers.flo_retriever import FloRagBuilder
from flo_ai.state.flo_session import FloSession
from flo_ai.retrievers.flo_compression_pipeline import FloCompressionPipeline
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.vectorstores import VectorStoreRetriever
from flo_ai.tools.flo_rag_retriver_tool import FloRagRetrieverTool

class FloPDFRagTool():

    def __init__(self) -> None:
        raise ValueError("You are supposed to use Builder, FloRagRetriverTool.Builder()")
    
    class Builder(FloRagRetrieverTool.Builder):
        def __init__(self) -> None:
            super().__init__()