from typing import Optional
from langchain_core.runnables import Runnable
from flo_ai.state.flo_session import FloSession
from flo_ai.models.flo_executable import ExecutableFlo, ExecutableType
from flo_ai.models.delegate import Delegate
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.language_models import BaseLanguageModel
from pydantic import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser


# TODO probably use messages to relay information
class NextAgent(BaseModel):
    next: str = Field(description='Name of the next member to be called')
    message: str = Field(description='Input to the next agent')


class FloDelegatorAgent(ExecutableFlo):
    def __init__(
        self,
        session: FloSession,
        executor: Runnable,
        delegate: Delegate,
        name: str,
        model_name: str,
    ) -> None:
        super().__init__(name, executor, ExecutableType.delegator)
        self.session = session
        self.delegate = delegate
        self.executor = executor
        self.model_name = model_name

    @staticmethod
    def create(
        session: FloSession,
        name: str,
        job: str,
        to: Delegate,
        llm: Optional[BaseLanguageModel] = None,
    ):
        model_name = 'default' if llm is None else llm.name
        return FloDelegatorAgent.Builder(
            session=session,
            name=name,
            job=job,
            delegate=to,
            llm=llm,
            model_name=model_name,
        ).build()

    class Builder:
        def __init__(
            self,
            session: FloSession,
            name: str,
            job: str,
            delegate: Delegate,
            llm: Optional[BaseLanguageModel] = None,
            model_name: str = None,
        ) -> None:
            self.session = session
            self.name = name
            self.to = delegate
            delegator_base_system_message = (
                'You are a delegator tasked with routing a conversation between the'
                ' following {member_type}: {members}. Given the following rules,'
                ' respond with the worker to act next. The output should be in strict JSON format. No non-JSON character should be in the output '
            )
            self.model_name = model_name
            self.llm = session.llm if llm is None else llm
            self.options = delegate.to
            self.parser = JsonOutputParser(pydantic_object=NextAgent)
            self.llm_router_prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        'system',
                        delegator_base_system_message
                        + '\n'
                        + 'Rules: {delegator_rules}'
                        + '\n'
                        + 'Given the conversation above, who should act next?'
                        + 'Select one of: {options} \n {format_instructions}',
                    ),
                    MessagesPlaceholder(variable_name='messages'),
                ]
            ).partial(
                options=str(self.options),
                members=', '.join(self.options),
                member_type='agents',
                delegator_rules=job,
                format_instructions=self.parser.get_format_instructions(),
            )

        def build(self):
            chain = self.llm_router_prompt | self.llm | self.parser

            return FloDelegatorAgent(
                session=self.session,
                name=self.name,
                delegate=self.to,
                executor=chain,
                model_name=self.model_name,
            )
