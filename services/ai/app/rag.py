"""
RAG retrieval for Eidovia, with HOE depth capping.

Embeddings come from one of two backends, chosen by the EMBED_BACKEND env var:
  - "local":  sentence-transformers all-MiniLM-L6-v2 (matches the current vectors)
  - "ollama": all-minilm served by Ollama (no PyTorch needed in this service)

The backend that embedded document_chunks must match the query backend.
Switching backends requires re-running scripts.load_curriculum.
"""

import asyncio
import logging
import os
from typing import Optional

import httpx
import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import config
from app.cache import cache_service

logger = logging.getLogger(__name__)

EMBED_BACKEND = os.getenv("EMBED_BACKEND", "local").lower()
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "all-minilm")
EMBED_TIMEOUT = float(os.getenv("EMBED_TIMEOUT", "30"))
EMBED_CACHE_TAG = (
    f"ollama:{OLLAMA_EMBED_MODEL}"
    if EMBED_BACKEND == "ollama"
    else f"local:{config.EMBEDDING_MODEL}"
)


class RAGService:
    """Embedding + pgvector retrieval, with an optional HOE depth cap."""

    def __init__(self):
        self.backend = EMBED_BACKEND
        self.model = None  # sentence-transformers model (local backend only)
        self.ready = False
        self.threshold = config.RAG_THRESHOLD
        self.top_k = config.RAG_TOP_K
        self.embedding_ttl = 3600
        self._http: Optional[httpx.AsyncClient] = None

    async def initialize(self) -> None:
        """Load the embedder. Must run before any encode or retrieve call."""
        if self.backend == "local":
            from sentence_transformers import SentenceTransformer  # imported lazily

            loop = asyncio.get_running_loop()
            self.model = await loop.run_in_executor(
                None, SentenceTransformer, config.EMBEDDING_MODEL
            )
            logger.info(f"Embedding backend: local ({config.EMBEDDING_MODEL})")

        elif self.backend == "ollama":
            self._http = httpx.AsyncClient(
                base_url=config.LLM_BASE_URL, timeout=EMBED_TIMEOUT
            )
            resp = await self._http.post(
                "/api/embed",
                json={"model": OLLAMA_EMBED_MODEL, "input": "warm-up"},
            )
            resp.raise_for_status()
            dim = len(resp.json()["embeddings"][0])
            if dim != config.EMBEDDING_DIMENSION:
                raise RuntimeError(
                    f"{OLLAMA_EMBED_MODEL} returned {dim} dimensions, "
                    f"expected {config.EMBEDDING_DIMENSION}"
                )
            logger.info(f"Embedding backend: ollama ({OLLAMA_EMBED_MODEL}, {dim}d)")

        else:
            raise RuntimeError(f"Unknown EMBED_BACKEND: {self.backend}")

        self.ready = True

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()

    async def _embed_raw(self, query: str) -> list[float]:
        if self.backend == "ollama":
            resp = await self._http.post(
                "/api/embed",
                json={"model": OLLAMA_EMBED_MODEL, "input": query},
            )
            resp.raise_for_status()
            return resp.json()["embeddings"][0]

        loop = asyncio.get_running_loop()
        vec = await asyncio.wait_for(
            loop.run_in_executor(None, self.model.encode, query),
            timeout=EMBED_TIMEOUT,
        )
        return vec.tolist()

    async def encode_query(self, query: str, use_cache: bool = True) -> np.ndarray:
        """Embed a query. Cache key includes the backend, so models never mix."""
        if not self.ready:
            raise RuntimeError("RAG service not initialized. Call initialize() first.")

        key = cache_service._make_key(f"embedding:{EMBED_CACHE_TAG}", query)
        if use_cache:
            cached = await cache_service.get(key)
            if cached and "embedding" in cached:
                return np.array(cached["embedding"], dtype=np.float32)

        try:
            vec = await self._embed_raw(query)
        except Exception as e:
            raise ValueError(f"Query encoding error: {e}") from e

        arr = np.array(vec, dtype=np.float32)
        await cache_service.set(key, {"embedding": arr.tolist()}, ttl=self.embedding_ttl)
        return arr

    async def retrieve_capped(
        self,
        session: AsyncSession,
        query_embedding: np.ndarray,
        max_level: Optional[int] = None,
        module_id: str = "DNA_BIOLOGY_001",
        k: Optional[int] = None,
    ) -> list[dict]:
        """
        Top-k chunks whose HOE level is <= max_level (None = no depth cap).

        Deliberately uncached: a cache key that ignores the level would return
        the same answer at every depth, which would invalidate the evaluation.
        """
        limit = k or self.top_k
        emb = str(query_embedding.tolist())

        if max_level is None:
            sql = text("""
                SELECT chunk_id, module_id, content, hoe_level,
                       1 - (embedding <=> CAST(:emb AS vector)) AS similarity
                FROM document_chunks
                WHERE module_id = :mod
                ORDER BY similarity DESC
                LIMIT :k
            """)
            params = {"emb": emb, "mod": module_id, "k": limit}
        else:
            sql = text("""
                SELECT chunk_id, module_id, content, hoe_level,
                       1 - (embedding <=> CAST(:emb AS vector)) AS similarity
                FROM document_chunks
                WHERE module_id = :mod AND hoe_level <= :lvl
                ORDER BY similarity DESC
                LIMIT :k
            """)
            params = {"emb": emb, "mod": module_id, "lvl": max_level, "k": limit}

        result = await session.execute(sql, params)

        docs = []
        for chunk_id, mod, content, level, similarity in result.fetchall():
            if similarity >= self.threshold:
                docs.append({
                    "chunk_id": str(chunk_id),
                    "module_id": mod,
                    "title": content.split(":", 1)[0].strip(),
                    "content": content,
                    "hoe_level": level,
                    "similarity": float(similarity),
                })

        logger.info(
            f"Retrieved {len(docs)}/{limit} chunks "
            f"(max_level={max_level}, backend={self.backend})"
        )
        return docs


# Global RAG service instance
rag_service = RAGService()