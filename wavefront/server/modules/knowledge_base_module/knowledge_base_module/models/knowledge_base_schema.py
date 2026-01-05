from pydantic import BaseModel
from typing import Optional


class NewKnowledge(BaseModel):
    name: str
    description: str
    type: str
    vector_size: int
    vector_size_1: Optional[int] = None


class NewInference(BaseModel):
    prompt: str
