from flo_ai import Flo
from flo_ai import FloSession
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from flo_ai.tools.flo_tool import flotool

from dotenv import load_dotenv
import warnings

load_dotenv()


warnings.simplefilter('default', DeprecationWarning)

gpt35 = ChatOpenAI(temperature=0, model_name='gpt-3.5-turbo')
gpt_4o_mini = ChatOpenAI(temperature=0, model_name='gpt-4o-mini')
gpt_4o = ChatOpenAI(temperature=0, model_name='gpt-4o')
session = FloSession(gpt35)

session.register_model('bronze', gpt35)
session.register_model('silver', gpt_4o_mini)
session.register_model('gold', gpt_4o)


class SendEmailInput(BaseModel):
    to: str = Field(
        description='Comma seperared list of users emails to which email needs to be sent'
    )
    message: str = Field(description='The email text to be sent')


@flotool(
    'email_triage',
    'useful for when you need to send an email to someone',
    argument_contract=SendEmailInput,
)
def email_tool(to: str, message: str):
    return f'Email sent successfully to: {to}'


session.register_tool('SendEmailTool', email_tool)

agent_yaml = """
apiVersion: flo/alpha-v1
kind: FloRoutedTeam
name: invite-handler
team:
    name: Personal-Assistant-Bot
    router:
        name: Personal-Assistant
        kind: supervisor
        model: silver
    agents:
      - name: EmailFriends
        job: You job is to send an invite to the christmas party at my house to my friends and friends only, not collegues, invite their spouses too. Keep the email warm and friendly.
        role: personal ai assistant
        model: bronze
        tools:
          - name: SendEmailTool
      - name: EmailColleagues
        job: You job is to send an invite to the christmas party at my house to my colleagues and not friends. Keep the email formal, and DO NOT invite the spouses.
        role: office ai assistant
        model: gold
        tools:
          - name: SendEmailTool
"""
input_prompt = """
Here is the list of user emails and there relations to me

vishnu@gmail.com / friend
nk@gmail.com / friend
jk@gmail.com / colleague
ck@hotmail.com / friend
hk@gmail.com / colleague
jak@gmail.com / colleague
ck@gmail.com / friend.

Please invite these nice folks to my christmas party
"""

flo: Flo = Flo.build(session, yaml=agent_yaml)
for s in flo.stream(input_prompt):
    if '__end__' not in s:
        print(s)
        print('----')
