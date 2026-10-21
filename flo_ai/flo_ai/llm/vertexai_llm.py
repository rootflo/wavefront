from typing import Optional, Dict, Any
from google import genai
from google.genai import types
from flo_ai.llm.gemini_llm import Gemini
from flo_ai.llm.base_llm import BaseLLM


class VertexAI(Gemini):
    def __init__(
        self,
        model: str = 'gemini-2.5-flash',
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        project: Optional[str] = None,
        location: Optional[str] = None,
        custom_headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        # Initialize only the BaseLLM part to avoid Gemini's client creation
        BaseLLM.__init__(self, model, api_key, temperature, **kwargs)

        # Store project, location, and base_url attributes
        self.project = project
        self.location = location
        self.base_url = base_url

        http_options: types.HttpOptionsDict = {'base_url': base_url} if base_url else {}
        if base_url and custom_headers:
            http_options['headers'] = dict(custom_headers)

        client_kwargs: Dict[str, Any] = {
            'project': project,
            'location': location,
            'vertexai': True,
        }
        if http_options:
            client_kwargs['http_options'] = http_options

        # Create VertexAI-specific client
        self.client = genai.Client(**client_kwargs)
