from langchain_core.output_parsers.openai_functions import JsonOutputFunctionsParser
from langchain.chains import LLMChain
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from typing import Union
from flo_ai.models.flo_member import FloMember
from flo_ai.state.flo_session import FloSession
from flo_ai.constants.prompt_constants import FLO_FINISH
from flo_ai.helpers.utils import randomize_name


# TODO, maybe add description about what team members can do
supervisor_system_message = (
    "You are a supervisor tasked with managing a conversation between the"
    " following {member_type}: {members}. Given the following user request,"
    " respond with the worker to act next. Each worker will perform a"
    " task and respond with their results and status. When the users question is answered or the assigned task is finished,"
    " respond with FINISH. If both your workers has responded atleast once, then strictly return FINISH "
)

class StateUpdateComponent:
        def __init__(self, name: str, session: FloSession) -> None:
            self.name = name
            self.inner_session = session

        def __call__(self, input):
            self.inner_session.append(self.name)
            return input


class FloSupervisor:
    def __init__(self,
                 executor: LLMChain, 
                 agents: list[FloMember],
                 name: str) -> None:
        self.executor = executor
        self.agents = agents
        self.name = name
        self.type = agents[0].type

    def is_agent_supervisor(self):
        return self.type == "agent"

class FloSupervisorBuilder:
    def __init__(self,
                 session: FloSession,
                 name: str,
                 reportees: list[FloMember],
                 supervisor_prompt: Union[ChatPromptTemplate, None] = None,
                 llm: Union[BaseLanguageModel, None] = None) -> None:
        # TODO add validation for reporteess
        self.name = randomize_name(name)
        self.session = session
        self.llm = llm if llm is not None else session.llm
        self.agents = reportees
        self.members = [agent.name for agent in reportees]
        self.options = self.members + [FLO_FINISH]
        member_type = "workers" if reportees[0].type == "agent" else "team members"
        self.supervisor_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", supervisor_system_message),
                MessagesPlaceholder(variable_name="messages"),
                (
                    "system",
                    "Given the conversation above, who should act next?"
                    " Or should we FINISH if the task is already answered, (do not wait for the entire question to be answered) or there isn't enough information to answer the question, even then return FINISH? Select one of: {options}",
                ),
            ]
        ).partial(options=str(self.options), members=", ".join(self.members), member_type=member_type) if supervisor_prompt is None else  supervisor_prompt
    
    def build(self):
        function_def = {
            "name": "route",
            "description": "Select the next role.",
            "parameters": {
                "title": "routeSchema",
                "type": "object",
                "properties": {
                    "next": {
                        "title": "Next",
                        "anyOf": [
                            {"enum": self.options},
                        ],
                    }
                },
                "required": ["next"],
            }
        }
            
        chain = (
            self.supervisor_prompt
            | self.llm.bind_functions(functions=[function_def], function_call="route")
            | JsonOutputFunctionsParser()
            | StateUpdateComponent(self.name, self.session)
        )

        return FloSupervisor(chain, self.agents, self.name)