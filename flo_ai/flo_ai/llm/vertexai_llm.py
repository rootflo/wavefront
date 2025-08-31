from typing import Optional
from google import genai
from flo_ai.llm.gemini_llm import Gemini
from flo_ai.llm.base_llm import BaseLLM


class VertexAI(Gemini):
    def __init__(
        self,
        model: str = 'gemini-2.5-flash',
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        base_url: str = None,
        project: str = None,
        location: str = None,
        **kwargs,
    ):
        # Initialize only the BaseLLM part to avoid Gemini's client creation
        BaseLLM.__init__(self, model, api_key, temperature, **kwargs)

        # Store project and location attributes
        self.project = project
        self.location = location

        # Create VertexAI-specific client
        self.client = genai.Client(project=project, location=location, vertexai=True)
