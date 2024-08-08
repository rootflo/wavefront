> **Warning**
>
> This project is under active development and we havent release any stable builds yet

# Flo: Composable AI Agents

Flo gives you a composable framework for creating agentic AI architectures. What we intent to do here is to create an easy framework for GenAI app developers to compose apps using pre-implemented architectural components, at the same time providing the flexibilty to create their own components.

### What is composibility ?

Composility is the ability to use smaller components to build bigger apps. In a composible architecture, you will be given smaller building blocks which you can use to build a bigger applications. It is every similar to how legos work, you are given smaller lego blocks which when put together creates a whole structure.

### What are the building blocks in Flo ?

In flo, we tried to put togther a system where we have small micro components like vector store, or simple LLM prompts, and then higher components/arhictectures made of these mico components like RAGs, Agentic Teams etc.

# Flo vs langraph/langchain

Flo is built with langraph under the stood. So everything that works in langraph still works here, including all tools and architectures. The following makes flo easy to implement:

1. Langraph needs good understanding of underlying graph and states, its a raw tool and asks developers to implement the required artitectures. While flo is more usecase friendly and components can be easily created by using the flo classes, which has lot of internal abstraction for ease of use.

2. In every AI component that has gone in production their are lot of nuances that needs to be implemented to get production quality output, flo inherently implements the best architecutures and gives them out of the box, you can enable and disable as you wish. This not only reduces the complexity but also improves the time to iterate solutions.

3. Every component in flo is combosable meaning you can easily put them together and flo takes care of routing between the components where as in langraph the developer has to tie these up.

# How to use
Flo supports two ways to set up and run the components, first is through code. This is much more flexible. This can help you write your own tools and add them to the flo.

Second way it to use yaml. You can write an yaml to define your agentic workflow or RAG and it compiles into a application. See examples below

## Building your first agent by structured yaml
To create a small team of researcher + blogger for writing blogs

```python
# This yaml defines a team of 2 agents + 1 supervisor
yaml_data = """
apiVersion: flo/alpha-v1
kind: FloRoutedTeam
name: blogging-team
team:
    name: BloggingTeam
    router:
        name: TeamLead
        kind: supervisor
    agents:
      - name: Researcher
        role: Researcher
        job: Do a research on the internet and find articles of relevent to the topic asked by the user, always try to find the latest information on the same
        tools:
        - name: TavilySearchResults
      - name: Blogger
        role: Writer
        job: From the documents provider by the researcher write a blog of 300 words with can be readily published, make in engaging and add reference links to original blogs
        tools:
        - name: TavilySearchResults
"""

input_prompt = """
Question: Write me an interesting blog about latest advancements in agentic AI
"""

llm = ChatOpenAI(temperature=0, model_name='gpt-4o')

# Register all the tools at some place and use everywhere in the yaml
session = FloSession(llm).register_tool(
    name="TavilySearchResults", 
    tool=TavilySearchResults()
)

# Build the final flow and run it
flo: Flo = Flo.build(session, yaml=yaml_data)

# call invoke or stream
for s in flo.stream(input_prompt)
```

## Building a RAG with flo

We are also made building RAG composable for ease of use. This RAG system can then be plugged into agentic flows and create a agentic solution, or be used independently.

```python
llm = ChatOpenAI(temperature=0, model_name='gpt-4o')
session = FloSession(llm)
# store in the vector store object you use, it can be any vector db like Chroma or Astra or Pinecorn etc
rag_builder = FloRagBuilder(session, store.as_retriever())

# this where you create a compression pipeline to easily add components like re-ranker
compression_pipeline = FloCompressionPipeline(OpenAIEmbeddings(model="<embeddings model>"))
compression_pipeline.add_embedding_reduntant_filter()
compression_pipeline.add_embedding_relevant_filter()


rag = rag_builder
   # Use custom prompt for your augmented generation
  .with_prompt(custom_prompt)
   # Enable multi-query to create multiple queries from the user query and bring all these semantically similar documents
  .with_multi_query()
  # Use compression to perform duplicate removal and re-ranking etc
  .with_compression(compression_pipeline)
  # Build the runnable rag
  .build_rag()

# Invoke the rag and get the output
print(rag.invoke({ "question": "What are the documents applying for housing loan" }))

# you can pass a chat history like this
print(rag.invoke({ "question": "What are the documents applying for housing loan", "chat_history": [] }))

```

## Making the RAG into tool

```python
rag_tool = rag_builder
  .with_multi_query()
  .build_rag_tool(name="RAGTool", description="RAG to answer question by looking at db")

# Invoke as tool or make it part of structured agentic flo
print(rag_tool.invoke({"query": "What is the interest rate on housing loans"}))
```

## Using RAG tool in Agentic flo

```python
# Register the tool to the existing session and add the tool to the previous yaml
session.register_tool(name="HousingLoanTool", tool=retriever_tool)

agent_yaml = """
apiVersion: flo/alpha-v1
kind: FloRoutedTeam
name: support-email-handler
team:
    name: SupportTicketHandler
    router:
        name: SupportSupervisor
        kind: supervisor
    agents:
      - name: EmailSender
        role: Email Sender
        job: You are capable of sending the reply email but constructing a apt response
        tools:
          - name: SendEmailTool
      - name: TransactionFetcher
        role: Transaction Fetcher
        job: You are capable of fetching any kind of transactions from the database given transaction reference id
        tools:
          - name: FetchTransactionTool
      - name: HousingLoanTeamLead
        role: Housing Loan Specialist
        job: Fetch the housing loan information from the db and answer the question
        tools:
          - name: HousingLoanTool
"""

flo: Flo = Flo.build(session, yaml=agent_yaml)
for s in flo.stream(input_prompt):
     if "__end__" not in s:
        print(s)
        print("----") 
```

# What next ?

