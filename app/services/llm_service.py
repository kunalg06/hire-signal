import os
import httpx
from google import genai
from google.genai import types

class LLMService:
    """Thin provider wrapper — swap models via GEMINI_MODEL env var."""

    _client = None

    @classmethod
    def get_client(cls) -> genai.Client:
        if cls._client is None:
            api_key = os.getenv('GEMINI_API_KEY', '').strip().strip('"').strip("'")
            if not api_key:
                raise ValueError("GEMINI_API_KEY not set in environment")
            cls._client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(httpx_client=httpx.Client(verify=False)),
            )
        return cls._client

    @classmethod
    def chat(cls, prompt: str, max_tokens: int = 2000) -> str:
        """Send a single user prompt and return the response text."""
        model = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
        response = cls.get_client().models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=max_tokens),
        )
        return response.text.strip()

    @classmethod
    def reset(cls):
        """Force client re-initialisation (useful in tests)."""
        cls._client = None
