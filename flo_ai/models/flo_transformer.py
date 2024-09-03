from flo_ai.models.flo_node import FloNode

class FloTransformer(FloNode):
    
    def __init__(self, func: object, name: str) -> None:
        super().__init__(func, name)