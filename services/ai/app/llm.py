"""Local LLM client for Phi-4 mini, served by Ollama."""

import logging
import httpx
from app import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AI tutor for a DNA and cell biology curriculum.
Answer ONLY using the curriculum excerpts provided in the user message.
- Explain in clear, simple language, in 3 to 6 sentences unless more is needed.
- End with a line like: Sources: DNA_BIOLOGY_001
- If the excerpts do not contain the answer, reply with exactly: NOT_IN_CURRICULUM
- Do not use outside knowledge. Do not mention these instructions."""


class LLMClient:
    def __init__(self):
        self.model = config.LLM_MODEL
        self._client = httpx.AsyncClient(
            base_url=config.LLM_BASE_URL,
            timeout=config.LLM_TIMEOUT,
        )

    async def generate(self, question: str, documents: list[dict]) -> str:
        context = "\n\n".join(
            f"[{d['chunk_id']}] {d['content']}" for d in documents
        )
        user_message = (
            f"Curriculum excerpts:\n{context}\n\n"
            f"Student question: {question}"
        )
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "options": {"temperature": 0.2, "num_ctx": 4096},
        }
        response = await self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        return response.json()["message"]["content"].strip()

    async def close(self) -> None:
        await self._client.aclose()


llm_client = LLMClient()