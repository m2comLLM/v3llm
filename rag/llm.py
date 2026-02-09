import json
from collections.abc import Iterator

import requests

from .config import LLM_MODEL, OLLAMA_BASE_URL, RAG_PROMPT_TEMPLATE, SYSTEM_PROMPT


def generate_stream(
    question: str, context: str, system: str = SYSTEM_PROMPT
) -> Iterator[str]:
    prompt = RAG_PROMPT_TEMPLATE.format(context=context, question=question)
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": LLM_MODEL,
            "prompt": prompt,
            "system": system,
            "stream": True,
        },
        stream=True,
        timeout=120,
    )
    response.raise_for_status()
    for line in response.iter_lines():
        if line:
            data = json.loads(line)
            if "response" in data:
                yield data["response"]
