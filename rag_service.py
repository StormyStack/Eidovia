"""
RAG Service Module
Handles document retrieval with cosine similarity guardrail.
Uses pgvector for efficient nearest-neighbor search.
"""

import logging
import asyncio
import numpy as np
from typing import Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sentence_transformers import SentenceTransformer

import config_prod as config

logger = logging.getLogger(__name__)

# ============================================================
# RAG SERVICE
# ============================================================

class RAGService:
    """
    Retrieval-Augmented Generation Service
    Handles document embedding, retrieval, and guardrail filtering.
    """
    
    def __init__(self):
        """Initialize RAG service with embedding model."""
        self.model: Optional[SentenceTransformer] = None
        self.threshold = config.RAG_THRESHOLD
        self.top_k = config.RAG_TOP_K
        self.timeout = config.RAG_TIMEOUT
        
    async def initialize(self) -> None:
        """
        Load embedding model asynchronously.
        Must be called before any retrieval operations.
        
        Raises:
            RuntimeError: If model fails to load
        """
        try:
            loop = asyncio.get_event_loop()
            self.model = await loop.run_in_executor(
                None,
                SentenceTransformer,
                config.EMBEDDING_MODEL
            )
            logger.info(f"✅ Embedding model loaded: {config.EMBEDDING_MODEL}")
        except Exception as e:
            logger.error(f"❌ Failed to load embedding model: {e}")
            raise RuntimeError(f"Embedding model initialization failed: {e}")
    
    async def encode_query(self, text: str) -> np.ndarray:
        """
        Encode query text to embedding vector.
        
        Args:
            text: Query text to encode
            
        Returns:
            384-dimensional embedding vector
            
        Raises:
            ValueError: If model not initialized or encoding fails
        """
        if self.model is None:
            raise ValueError("RAG service not initialized. Call initialize() first.")
        
        try:
            loop = asyncio.get_event_loop()
            embedding = await asyncio.wait_for(
                loop.run_in_executor(None, self.model.encode, text),
                timeout=self.timeout
            )
            return np.array(embedding, dtype=np.float32)
        except asyncio.TimeoutError:
            logger.error(f"Encoding timeout for query: {text[:50]}...")
            raise ValueError("Query encoding timeout")
        except Exception as e:
            logger.error(f"Query encoding failed: {e}")
            raise ValueError(f"Query encoding error: {e}")
    
    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        Compute cosine similarity between two vectors.
        
        Args:
            vec1: First vector
            vec2: Second vector
            
        Returns:
            Cosine similarity score in [0, 1]
        """
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 < 1e-10 or norm2 < 1e-10:
            return 0.0
        
        similarity = np.dot(vec1, vec2) / (norm1 * norm2)
        return float(np.clip(similarity, 0.0, 1.0))
    
    async def retrieve_documents(
        self,
        session: AsyncSession,
        query_embedding: np.ndarray,
        module_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> list[dict]:
        """
        Retrieve top-k documents by cosine similarity (using pgvector).
        
        Args:
            session: Database session
            query_embedding: Query embedding vector
            module_id: Optional filter by module
            limit: Override default top_k
            
        Returns:
            List of documents with similarity scores, empty if all below threshold
            
        Raises:
            Exception: If database query fails
        """
        from sqlalchemy import func, text
        
        try:
            k = limit or self.top_k
            
            # Use pgvector's <=> operator for cosine distance (ascending)
            query_str = """
                SELECT 
                    chunk_id, 
                    module_id, 
                    content,
                    1 - (embedding <=> :query_vec::vector) AS similarity
                FROM document_chunks
            """
            
            params = {"query_vec": query_embedding.tobytes().hex()}
            
            if module_id:
                query_str += " WHERE module_id = :module_id"
                params["module_id"] = module_id
            
            query_str += " ORDER BY similarity DESC LIMIT :limit"
            params["limit"] = k
            
            result = await session.execute(text(query_str), params)
            rows = result.fetchall()
            
            documents = []
            for row in rows:
                chunk_id, mod_id, content, similarity = row
                
                # Apply guardrail threshold
                if similarity >= self.threshold:
                    documents.append({
                        "chunk_id": str(chunk_id),
                        "module_id": mod_id,
                        "content": content,
                        "similarity": float(similarity)
                    })
                else:
                    logger.debug(
                        f"Document below threshold: similarity={similarity:.3f}, "
                        f"threshold={self.threshold}"
                    )
            
            logger.info(
                f"Retrieved {len(documents)}/{k} documents "
                f"(threshold={self.threshold}, max_similarity={max([d['similarity'] for d in documents] or [0.0]):.3f})"
            )
            
            return documents
            
        except Exception as e:
            logger.error(f"Document retrieval failed: {e}")
            raise
    
    async def is_on_topic(
        self,
        query_embedding: np.ndarray,
        max_similarity: float
    ) -> bool:
        """
        Determine if query is on-topic based on max similarity to known documents.
        
        Args:
            query_embedding: Query embedding
            max_similarity: Maximum similarity score from retrieval
            
        Returns:
            True if on-topic (above threshold), False otherwise
        """
        is_topic = max_similarity >= self.threshold
        logger.debug(f"On-topic check: {is_topic} (similarity={max_similarity:.3f})")
        return is_topic
    
    async def build_context(
        self,
        session: AsyncSession,
        query: str,
        query_embedding: np.ndarray
    ) -> dict:
        """
        Build complete RAG context for a query.
        
        Args:
            session: Database session
            query: User query text
            query_embedding: Query embedding
            
        Returns:
            Dictionary with context, on-topic status, and metadata
            
        Example:
            {
                "is_on_topic": True,
                "max_similarity": 0.78,
                "documents": [...],
                "context": "Document chunk text...",
                "error": None
            }
        """
        try:
            documents = await self.retrieve_documents(
                session,
                query_embedding
            )
            
            max_similarity = max(
                [d["similarity"] for d in documents],
                default=0.0
            )
            
            is_topic = await self.is_on_topic(query_embedding, max_similarity)
            
            # Build context string from retrieved documents
            context_parts = []
            for doc in documents:
                context_parts.append(
                    f"[{doc['module_id']}] {doc['content']}"
                )
            
            context = "\n\n".join(context_parts) if context_parts else ""
            
            return {
                "is_on_topic": is_topic,
                "max_similarity": max_similarity,
                "num_documents": len(documents),
                "documents": documents,
                "context": context,
                "error": None,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Context building failed: {e}")
            return {
                "is_on_topic": False,
                "max_similarity": 0.0,
                "num_documents": 0,
                "documents": [],
                "context": "",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


# Global RAG service instance
rag_service = RAGService()
