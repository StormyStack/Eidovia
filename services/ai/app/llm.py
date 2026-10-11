"""Local LLM client for Phi-4 mini (Ollama), with HOE depth control."""

import logging
import httpx
from app import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AI tutor for a DNA and cell biology curriculum.
Answer ONLY using the curriculum excerpts in the user message.
- Follow the depth instruction in the user message.
- Use clear, simple language.
- If the excerpts do not contain the answer, reply with exactly: NOT_IN_CURRICULUM
- Do not write a Sources line. Do not use outside knowledge. Do not mention these instructions."""

DEPTH_INSTRUCTIONS = {
    None: "Answer at a clear, general level in 3 to 6 sentences.",
    1: "Give a short overview only, in 2 to 3 sentences. Do not explain mechanisms or molecular details.",
    2: "Explain the structural parts and how they fit together, in 3 to 5 sentences.",
    3: "Explain the components and how they interact, naming the specific parts involved.",
    4: "Explain the molecular mechanism step by step, naming the enzymes and molecules involved.",
}


class LLMClient:
    def __init__(self):
        self.model = config.LLM_MODEL
        self._client = httpx.AsyncClient(
            base_url=config.LLM_BASE_URL,
            timeout=config.LLM_TIMEOUT,
        )

    async def generate(self, question: str, documents: list[dict], hoe_level=None) -> str:
        context = "\n\n".join(f"[{d['title']}] {d['content']}" for d in documents)
        user_message = (
            f"Depth: {DEPTH_INSTRUCTIONS[hoe_level]}\n\n"
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