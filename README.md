
# Table of contents

1. [Installation](#installation)
2. [Flo: Composable AI Agents ?](#flo-composable-ai-agents)
3. [Getting Started](#getting-started)
4. [Building your first agent](#building-your-first-agent)
5. [Building a RAG with flo](#building-a-rag-with-flo)
6. [Understanding Flo Deeper](#understanding-flo-deeper)

# Installation

Using pip:

```cmd
pip install flo-ai
```
Using poetry:

```cmd
poetry add flo-ai
```
Importing:

```cmd
from flo_ai import Flo, FloSession
```

# Flo: Composable AI Agents

Flo gives you a composable framework for creating agentic AI architectures. What we intend to do here is to create an easy framework for GenAI app developers to compose apps using pre-implemented architectural components while providing the flexibility to create their components.

### Composability

Composability is the ability to use smaller components to build more composable applications. In a composible architecture, you will be given smaller building blocks which you can use to build you bigger component, or the final application. It is very similar to how legos work, you are given the smaller Lego blocks which when put together create a whole building.

### Building blocks

In flo, we tried to put together a system where we have small micro components like vector store, or simple LLM prompts, and then higher components/architectures made of these micro components like RAGs, Agentic Teams etc.

### Flo vs langraph or crew-ai

Flo is built with langraph working under the hood. So everything that works in langraph or langchain still works here, including all tools and architectures. The following makes flo a better solution:

1. Langraph needs a good understanding of the underlying graphs and states, its a raw tool and asks developers to implement the required components. While flo is more use-case friendly and components can be easily created by using the flo classes, which have lot of internal abstraction for ease of use.

2. In every AI component that has gone into production there are a lot of nuances that need to be implemented to get production-quality output, flo inherently implements these architectures and gives them out of the box, you can enable and disable as you wish. This not only reduces the complexity but also improves the time to iterate solutions.

3. Every component in flo is combosable meaning you can easily put them together and flo takes care of routing between the components whereas in langraph the developer has to tie these up. Flo plans to support custom routers in the future

# Getting Started

Flo supports two ways to set up and run the components, first is through code. This is flexible and but still not a first class citizen, as we are actively working to make it better. This can help you write your own tools and add them to the flo.

Second way is to use yaml. You can write an yaml to define your agentic workflow and it compiles into an application. See examples below.

## Building your first agent

To create a small team of researcher + blogger for writing blogs

```python
from flo_ai import Flo
from flo_ai import FloSession
from langchain_openai import ChatOpenAI

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
        job: Do research on the internet and find articles of relevent to the topic asked by the user, always try to find the latest information on the same
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

# Register all the tools within the session and use them everywhere in the yaml
session = FloSession(llm).register_tool(
    name="TavilySearchResults", 
    tool=TavilySearchResults()
)

# Build the final flow and run it
flo: Flo = Flo.build(session, yaml=yaml_data)

# call invoke or stream
flo.stream(input_prompt)
```

Create a simple agent

```python

# define all you tools PurchaseTool, LoanRequestTool etc

agent_yaml = """
apiVersion: flo/alpha-v1
kind: FloAgent
name: banking-assistant
agent:
    name: BankingCustomer
    job: >
      You have the capability to interact with the bank in different ways. Depending upon your need take the right actions
    tools:
      - name: PurchaseTool
      - name: LoanRequestTool
      - name: CustomerSupportTool
"""

# set you session, register tools and trigger agent
```

## Building a RAG with flo

We are also made building RAG composable. This RAG system can then be plugged into agentic flows and create an agentic RAG, or be used independently.

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

### Making the RAG into tool

Making agentic RAG tool is easy in flo

```python
rag_tool = rag_builder
  .with_multi_query()
  .build_rag_tool(name="RAGTool", description="RAG to answer question by looking at db")
```

### Using RAG tool in Agentic flo

Once you create the tool, register the tool and use the same to build your flo

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

# Advanced Implementation

Lets breakdown the structure of the yaml.

| Name | Description |
|------|-------------|
|kind  | The type of agentic flo. You have two options here, `FloRoutedTeam` or `FloAgent`|
|name  | This is the name of the agentic flo
|team/agent | The next key can be a `team` or an `agent` depending on whether you plan to create a team or an single agent|
|team.router | Router this a component which manages the task in a team. The router takes care of properly routing the task, or sub-dividing the task depending on the current state. Currently we only support `supervisor`, `linear`, `llm` as routers, more types are under construction|
|(team/agent).name  | This is the name of the team or agent. The name should be an alpanumeric without spaces
|agent.job | This is the job that is expected to be done by the agent. |
|agent.role | This will assign a persona to the agent. This field is optional
|agent.tools | List of tools available to the agent.

### FloSession

This is the current session in which flo is running. The session helps keep track of current execution and handles loops etc. We plan to add more control variables into sessions. Right now, the LLM to be used & tools available are configured within the session

```python
# you can keep registering more and more tools
session = FloSession(llm).register_tool(
    name="TavilySearchResults", 
    tool=TavilySearchResults()
)
```

### Agents
The smallest component we have is an agent. It consist of the job to be done, a role, and its tools

```yaml
name: HousingLoanTeamLead
role: Housing Loan Specialist
job: Fetch the housing loan information from the db and answer the question
tools:
  - name: HousingLoanTool
```
Using just this agent you can create an agent flo, and it becomes ready for execution

```yaml
apiVersion: flo/alpha-v1
kind: FloAgent
name: banking-assistant
agent:
    name: HousingLoanTeamLead
    kind: llm
    role: Housing Loan Specialist
    job: Fetch the housing loan information from the db and answer the question
    tools:
      - name: HousingLoanTool
```

#### Agent Types:

Flo AI now supports different types of agents which are intended for different purposes or use-case. You can choose these components to customize your workflow. You can specify the type of agents by specifiying `kind` param within agent block of the yaml (like the above once).

| kind | functionality |
|------|---------------|
| agentic | This is the default kind, these are default agents with a tool associated with them. These kinds of agents always needs tool or it will throw na exception|
| llm | These are agents without tools, they can work with current state of the execution, and do their job|
| reflection | These agents have the ability to reflect on the current result and retry a previous step
| delegation | These agents can delegate the current flow to a agent based on a prompt.

Note: `reflection` and `delegation` are implemented with linear router only right now. The support will be extended to other routers in next release

### Routers
Routers are the piller stone to how the flo is executed. They decided how the agents are connected. You can configure a router type by changing `kind` in the router component of the yaml. Right now we support the following routers:

| Router | Functionality |
|--------|---------------|
| supervisor | In this type of router all the agents are connected in a heirarchical fashion to the router and the router decides whom to call when.
| linear | In the type of routing the agents are executed in linear fashion from one node to another based on the order. Linear routing also supports `delegators` and `reflection` agents for re-routing the flow
| llm | In this type of routing the routing is based on the provided prompt| 

### Team

A team is a group fo agents working towards a common goal. A team has to have a router to manage things, just like a manager your workplace. Right now we support `supervisor` as your router, but more types are on the way.

```yaml
apiVersion: flo/alpha-v1
kind: FloRoutedTeam
name: support-email-handler
team:
    name: SupportTicketHandler
    router:
        name: SupportSupervisor
        kind: supervisor
    agents:
      - name: HousingLoanTeamLead
        role: Housing Loan Specialist
        job: Fetch the housing loan information from the db and answer the question
        tools:
          - name: HousingLoanTool
```
Teams can also have sub-teams, for example:

```yaml
apiVersion: flo/alpha-v1
kind: FloRoutedTeam
name: blogging-team
team:
    name: BloggingTeam
    supervisor:
        name: supervisor
        kind: supervisor
    subteams:
        - name: BloggingTeam
          supervisor:
            name: supervisor
            kind: supervisor
          agents:
            - name: Reasercher
              job: Do a research on the internet and find articles of relevent to the topic asked by the user, always try to find the latest information on the same
              tools:
              - name: TavilySearchResults
            - name: Blogger
              job: From the documents provider by the researcher write a blog of 300 words with can be readily published, make in engaging and add reference links to original blogs
              tools:
                - name: TavilySearchResults
        - name: Writing Team
          supervisor:
            name: supervisor
            kind: supervisor
          agents: 
            - name: Figure
              job: Do somethinh
              tools:
                - name: TavilySearchResults
```
This is the composability has flo unlocks, you can keep doing broader or deeper. We plan to make the yamls composable by building seperate testable agents that can be combined. 

# Contributions

FloAI is open-source and we welcome contributions. If you're looking to contribute, please:

1. Fork the repository.
2. Create a new branch for your feature.
3. Add your feature or improvement.
4. Send a pull request.

We appreciate your input!

## Installing Dependencies

```cmd
poetry lock
poetry install
```

# License
FloAI is released under the MIT License.




