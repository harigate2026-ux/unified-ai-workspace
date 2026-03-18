"""LLM calls using Groq (OpenAI-compatible)."""

#from openai import AsyncOpenAI
from groq import AsyncGroq
from app.config import get_settings

_settings = get_settings()
_groq: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _groq
    if _groq is None:
        _groq = AsyncGroq(
            api_key=_settings.groq_api_key or "not-set",
            base_url=_settings.groq_api_base,
        )
    return _groq


async def chat_completion(system: str, user_message: str) -> str:
    """Single turn: system + user message, return assistant content."""
    try:
        client = _get_client()

        resp = await client.chat.completions.create(
            model=_settings.groq_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            max_tokens=1024,
        )

        if not resp.choices:
            return ""

        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"LLM Error: {e}")
        return f"I'm sorry, I encountered an error while processing your request. Please ensure LLM API keys are configured properly. Error: {str(e)}"