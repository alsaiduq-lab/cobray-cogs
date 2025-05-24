import os
import logging
from openai import AsyncOpenAI
from . import parser

log = logging.getLogger("red.latex.ai")

XAI_API_KEY = os.environ.get("XAI_API_KEY")
XAI_API_BASE = os.environ.get("XAI_API_BASE", "https://api.x.ai/v1")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_API_BASE = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")


def is_configured() -> bool:
    return bool(XAI_API_KEY) or bool(OPENAI_API_KEY)


async def question_to_latex(question: str, provider: str = "xai", model: str = None) -> tuple[str, str]:
    if provider == "xai":
        if not XAI_API_KEY:
            raise RuntimeError("Grok (xAI) API key not set as XAI_API_KEY.")
        client = AsyncOpenAI(api_key=XAI_API_KEY, base_url=XAI_API_BASE)
        default_model = "grok-3-fast"
    elif provider == "openai":
        if not OPENAI_API_KEY:
            raise RuntimeError("OpenAI API key not set as OPENAI_API_KEY.")
        client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)
        default_model = "gpt-4.1"
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    selected_model = model if model else default_model

    try:
        response = await client.chat.completions.create(
            model=selected_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert math tutor. For every user question, reply with only a single correct LaTeX math expression (no explanation). Use '\\infty' for infinity. Wrap fractions and roots in correct LaTeX syntax."
                    ),
                },
                {"role": "user", "content": f"Convert this math question to a single LaTeX expression: {question}"},
            ],
            max_tokens=300,
            temperature=0,
        )
        latex_code = response.choices[0].message.content.strip()
        normalized = parser.normalize_latex(latex_code)
        return normalized, "there are mfers charging 2 dollars for ts, make sure to say thanks"
    except Exception as e:
        log.exception(f"{provider.upper()} API error: {e}")
        raise
