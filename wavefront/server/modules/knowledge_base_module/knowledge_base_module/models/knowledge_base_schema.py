from pydantic import BaseModel
from typing import Optional


class NewKnowledge(BaseModel):
    name: str
    description: str
    type: str
    vector_size: int
    vector_size_1: Optional[int] = None


class UpdateKnowledge(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None


class NewInference(BaseModel):
    prompt: str
