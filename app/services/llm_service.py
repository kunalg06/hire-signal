import os
import httpx
from openai import OpenAI

class LLMService:
    """Thin provider wrapper — swap models/providers via OPENROUTER_MODEL env var."""

    _client = None

    @classmethod
    def get_client(cls) -> OpenAI:
        if cls._client is None:
            api_key = os.getenv('OPENROUTER_API_KEY', '').strip().strip('"').strip("'")
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY not set in environment")
            cls._client = OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://github.com/kunalg06/hire-signal",
                    "X-Title": "hire-signal",
                },
                http_client=httpx.Client(verify=False),
            )
        return cls._client

    @classmethod
    def chat(cls, prompt: str, max_tokens: int = 2000) -> str:
        """Send a single user prompt and return the response text."""
        model = os.getenv('OPENROUTER_MODEL', 'anthropic/claude-haiku-4-5')
        response = cls.get_client().chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()

    @classmethod
    def reset(cls):
        """Force client re-initialisation (useful in tests)."""
        cls._client = None
