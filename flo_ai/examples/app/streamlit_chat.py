import os
import boto3
import yaml
import json
import time
import streamlit as st
from typing import Dict, Any
from pydantic import Field, BaseModel
from langchain_aws import ChatBedrock

from flo_ai.tools import flotool
from flo_ai import FloSession, Flo
from flo_ai_tools import RedshiftConnector, RedshiftConfig

redshift = RedshiftConnector(
    RedshiftConfig(
        username=os.getenv('REDSHIFT_USERNAME'),
        password=os.getenv('REDSHIFT_PASSWORD'),
        host=os.getenv('REDSHIFT_HOST'),
        port=os.getenv('REDSHIFT_PORT'),
        db_name=os.getenv('REDSHIFT_DB'),
    )
)

AWS_REGION = os.getenv('AWS_REGION')
AWS_BEDROCK_MODEL_ID = os.getenv('AWS_BEDROCK_MODEL_ID')
bedrock_client = boto3.client(service_name='bedrock-runtime', region_name=AWS_REGION)

with open('./examples/data/schema.yaml') as f:
    schema = yaml.safe_load(f)

columns = schema['columns']
columns_with_desc = [col for col in columns if col['description'] is not None]
schema['columns'] = columns_with_desc

bedrock_chat = ChatBedrock(
    client=bedrock_client,
    provider='anthropic',
    model_id=AWS_BEDROCK_MODEL_ID,
    region_name=AWS_REGION,
    model_kwargs={'temperature': 0.2, 'max_tokens': 4000},
)


class RedshiftQueryToolInput(BaseModel):
    query: str = Field(
        ...,
        description='The query to be run on reshift db. All queries should use proper column projections to use only the minimum required columns',
    )


@flotool(
    name='RedshiftQueryTool',
    description='This tool has the ability to run queries on Redshift DB',
    argument_contract=RedshiftQueryToolInput,
)
def redshift_execution_tool(query: str):
    results, column_names = redshift.execute_query(query=query)
    output = []
    for result in results:
        row = []
        for i, column in enumerate(column_names):
            row.append(f'{column}: {result[i]}')
        output.append('\n'.join(row))
    full_text = '\n ---- \n'.join(output)
    print(f'Here is the response fro the db: {full_text}')
    return f'Here is the response fro the db: {full_text}'


yaml_data = """
apiVersion: flo/alpha-v1
kind: FloRoutedTeam
name: analytics-flo
team:
    name: AnalyticsTeam
    agents:
      - name: AnalyticsDelegator
        kind: delegator
        role: analytics team manager
        to:
          - name: Analyst
          - name: AnalyticsPresenter
        job: >
          Your job is to understand the users question and delegate to the right agent
          If the question is very generic, ask the AnalyticsPresenter to ask the user about more specific details, 
          to clarify the question.
          If the question can be answered from the database, ask the Analyst

          eg:
          "How did we perform this week compared to last week" - then the you should confirm the understanding of "performance" before going forward - "By performance, do you mean First Call Resolution, Average Handler Time or something else?"

      - name: Analyst
        kind: agentic
        role: expert in writing and executing Redshift Queries
        job: >
          Your job is to understand the human question, and answer the question.
          You can use the given tools to query data from the redshift
        tools:
            - name: RedshiftQueryTool

      - name: AnalyticsPresenter
        kind: llm
        role: expert product manager
        job: >
          If the assistant has given an answer, summarize it and return the answer as if you are talking to a product manager
          If you needs more information, ask for the same. Always produce a good answer, this output will be show on the UI
    router:
      name: router
      kind: linear
"""

session = FloSession(bedrock_chat).register_tool(
    name='RedshiftQueryTool', tool=redshift_execution_tool
)

flo: Flo = Flo.build(session, yaml=yaml_data)

# Initialize session state for messages
if 'messages' not in st.session_state:
    st.session_state.messages = []


def parse_stream_response(response) -> Dict[str, Any]:
    """Parse the stream response and extract relevant content."""
    try:
        # Extract the message content based on the response structure
        if 'AnalyticsDelegator' in response:
            return {
                'role': 'assistant',
                'content': response['AnalyticsDelegator']['messages'][-1],
                'type': 'query',
            }
        elif 'Analyst' in response:
            # Extract the text content from the HumanMessage
            message = response['Analyst']['messages'][-1].content[0]['text']
            return {'role': 'assistant', 'content': message, 'type': 'analysis'}
        elif 'AnalyticsPresenter' in response:
            # Extract the presenter's message
            message = response['AnalyticsPresenter']['messages'][-1].content
            return {'role': 'assistant', 'content': message, 'type': 'summary'}
        return None
    except json.JSONDecodeError:
        # If it's not JSON, it might be the raw data response
        if 'product:' in response:
            return {'role': 'assistant', 'content': response, 'type': 'data'}
        return None


def process_analytics_query(query: str, placeholder):
    """Process the analytics query using flo.stream."""
    loading_messages = {
        'query': '🔍 Analyzing your question...',
        'data': '📊 Fetching data...',
        'analysis': '🧮 Processing analysis...',
        'summary': '📝 Preparing summary...',
    }
    try:
        prompt = f"""
            {query}

            Below is the schema of the table:
            {json.dumps(schema)}
        """
        # Stream the responses
        for response in flo.stream(prompt):
            # Show loading message
            with placeholder:
                st.write(loading_messages.get('query', 'Processing...'))
                with st.spinner(''):
                    time.sleep(1)  # Add slight delay for visual feedback
                st.empty()  # Clear the loading message
            if '__end__' not in response:
                parsed_response = parse_stream_response(response)
                if parsed_response:
                    yield parsed_response

                    # Show next stage loading message if not the last response
                    next_type = None
                    if parsed_response['type'] == 'query':
                        next_type = 'data'
                    elif parsed_response['type'] == 'data':
                        next_type = 'analysis'
                    elif parsed_response['type'] == 'analysis':
                        next_type = 'summary'

                    if next_type:
                        with placeholder:
                            st.write(loading_messages.get(next_type, 'Processing...'))
                            with st.spinner(''):
                                time.sleep(1)  # Add slight delay for visual feedback
                            st.empty()  # Clear the loading message
    except Exception as e:
        yield {
            'role': 'assistant',
            'content': f'Error processing query: {str(e)}',
            'type': 'error',
        }


# Streamlit UI
st.title('Analytics Chat Interface')

# Sidebar with information
with st.sidebar:
    st.markdown("""
    ### Analytics Assistant
    Ask questions about:
    - Product escalation rates
    - Customer complaints
    - Service metrics
    
    The assistant will provide:
    1. Data analysis
    2. Key insights
    3. Recommendations
    """)

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message['role']):
        st.markdown(message['content'])

# Create a placeholder for loading messages
loading_placeholder = st.empty()

# Chat input
if prompt := st.chat_input('What would you like to analyze?'):
    # Add user message to chat
    st.session_state.messages.append({'role': 'user', 'content': prompt})
    with st.chat_message('user'):
        st.markdown(prompt)

    # Process the query and display streaming responses
    for response in process_analytics_query(prompt, loading_placeholder):
        st.session_state.messages.append(response)
        with st.chat_message('assistant'):
            if response['type'] == 'data':
                # Format raw data in a more readable way
                formatted_data = response['content'].replace(
                    '\n', '  \n'
                )  # Add markdown line breaks
                st.markdown(f'```\n{formatted_data}\n```')
            else:
                st.markdown(response['content'])

# Add clear chat button
if st.sidebar.button('Clear Chat'):
    st.session_state.messages = []
    st.rerun()
