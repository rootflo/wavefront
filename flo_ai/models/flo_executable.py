from flo_ai.models.flo_member import FloMember
from langchain_core.runnables import Runnable
from langchain_core.messages import HumanMessage

class ExecutableFlo(FloMember):
    def __init__(self, 
                 name: str, 
                 runnable: Runnable, 
                 type: str = "team") -> None:
        super().__init__(name, type)
        self.runnable = runnable

    def stream(self, work, config = None):
        return self.runnable.stream({
             "messages": [
                HumanMessage(content=work)
            ]
        }, config)
    
    def invoke(self, work, config = None):
        return self.runnable.invoke({
             "messages": [
                HumanMessage(content=work)
            ]
        }, config)