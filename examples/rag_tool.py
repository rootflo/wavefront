from flo_ai import Flo
from flo_ai import FloSession
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings.sentence_transformer import (
    SentenceTransformerEmbeddings,
)
from langchain_text_splitters import CharacterTextSplitter

from dotenv import load_dotenv
from flo_ai.retrievers.flo_retriever import FloRagBuilder
from flo_ai.retrievers.flo_compression_pipeline import FloCompressionPipeline


load_dotenv()


llm = ChatOpenAI(temperature=0, model_name='gpt-4o-mini')

session = FloSession(llm, log_level='ERROR')

# load the document and split it into chunks
loader = TextLoader('./examples/rag_document.txt')
documents = loader.load()

# split it into chunks
text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
docs = text_splitter.split_documents(documents)

# create the open-source embedding function
embedding_function = SentenceTransformerEmbeddings(model_name='all-MiniLM-L6-v2')

# load it into Chroma
db = Chroma.from_documents(docs, embedding_function)


llm = ChatOpenAI(temperature=0, model_name='gpt-4o-mini')
session = FloSession(llm)
builder = FloRagBuilder(session, db.as_retriever())
compression_pipeline = FloCompressionPipeline(
    OpenAIEmbeddings(model='text-embedding-3-small')
)
compression_pipeline.add_embedding_reduntant_filter()
compression_pipeline.add_embedding_relevant_filter()
# Reranking

retriever_tool = builder.with_compression(compression_pipeline).build_rag_tool(
    name='HousingLoanRetreiver', description='Tool to fetch data around housing loans'
)
session.register_tool(name='HousingLoanTool', tool=retriever_tool)

simple_tool_agent = """
apiVersion: flo/alpha-v1
kind: FloAgent
name: llm-assistant
agent:
    name: tool-get-loan
    kind: agentic
    job: To retrieve and answer user questions
    tools:
        - name: HousingLoanTool
"""

flo = Flo.build(session, simple_tool_agent)

print(flo.invoke('Whats interest rate on loan'))
