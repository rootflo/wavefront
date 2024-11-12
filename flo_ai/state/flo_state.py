from typing import Annotated, List, Sequence, TypedDict, Tuple
from langchain_core.messages import BaseMessage


import operator

STATE_NAME_LOOP_CONTROLLER = 'loop_tracker'
STATE_NAME_NEXT = 'next'
STATE_NAME_MESSAGES = 'messages'


# The agent state is the input to each node in the graph
class TeamFloAgentState(TypedDict):
    # The annotation tells the graph that new messages will always
    # be added to the current states
    messages: Annotated[Sequence[BaseMessage], operator.add]
    # The 'next' field indicates where to route to next
    next: str
    # used for reflection agents
    loop_tracker: dict


class TeamFloAgentStateWithPlan(TypedDict):
    input: str
    plan: List[str]
    past_steps: Annotated[List[Tuple], operator.add]
    response: str
