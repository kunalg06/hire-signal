import os
from google import genai
from google.genai import types
from app.config import Config

class LLMService:
    """Thin provider wrapper — swap models via GEMINI_MODEL env var."""

    _client = None

    @classmethod
    def get_client(cls) -> genai.Client:
        if cls._client is None:
            api_key = os.getenv('GEMINI_API_KEY', '').strip().strip('"').strip("'")
            if not api_key:
                raise ValueError("GEMINI_API_KEY not set in environment")
            client_kwargs = {'api_key': api_key}
            if Config.GEMINI_TLS_SKIP_VERIFY:
                import httpx
                client_kwargs['http_options'] = types.HttpOptions(
                    httpx_client=httpx.Client(verify=False))
            cls._client = genai.Client(**client_kwargs)
        return cls._client

    @classmethod
    def chat(cls, prompt: str, max_tokens: int = 2000, response_schema: dict = None) -> str:
        """Send a single user prompt and return the response text.

        Every current caller parses the reply as JSON. response_mime_type
        alone is not reliable for long string fields (e.g. multi-line code
        in a "starter_code" value) — the model can still emit unescaped
        literal newlines there, which breaks json.loads with "Invalid
        control character" / "Unterminated string". Passing response_schema
        forces Gemini's constrained structured-output decoding, which was
        verified (14/14 live runs) to escape string content correctly where
        response_mime_type alone failed intermittently.
        """
        model = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
        config_kwargs = {
            'max_output_tokens': max_tokens,
            # gemini-2.5-flash+ spend "thinking" tokens out of the same
            # max_output_tokens budget as the visible reply — left enabled,
            # a long-enough internal thinking pass silently truncates the
            # JSON response before the closing brace.
            'thinking_config': types.ThinkingConfig(thinking_budget=0),
            'response_mime_type': 'application/json',
        }
        if response_schema is not None:
            config_kwargs['response_schema'] = response_schema
        response = cls.get_client().models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        return response.text.strip()

    @classmethod
    def reset(cls):
        """Force client re-initialisation (useful in tests)."""
        cls._client = None
