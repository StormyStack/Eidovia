"""
RAG Service Module (Cache-First Strategy with Fixed pgvector Query)
Handles document retrieval with Redis caching layer.
Uses pgvector for efficient nearest-neighbor search.

Request Flow:
1. Check Redis cache (fast, <10ms)
2. If miss, query PostgreSQL (slower, <100ms)
3. Store result in Redis
4. Return to client
"""

import logging
import asyncio
import json
import numpy as np
from typing import Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sentence_transformers import SentenceTransformer

import config_prod as config
from cache_service import cache_service

logger = logging.getLogger(__name__)

# ============================================================
# RAG SERVICE WITH REDIS CACHING & FIXED PGVECTOR QUERY
# ============================================================

class RAGService:
    """
    Retrieval-Augmented Generation Service with Cache-First Strategy
    
    Caching Strategy:
    - Query Embeddings: Cached for 1 hour
    - Retrieved Documents: Cached for 1 hour
    - Context: Cached per query for 30 minutes
    """
    
    def __init__(self):
        """Initialize RAG service with embedding model."""
        self.model: Optional[SentenceTransformer] = None
        self.threshold = config.RAG_THRESHOLD
        self.top_k = config.RAG_TOP_K
        self.timeout = config.RAG_TIMEOUT
        
        # Cache TTLs
        self.embedding_ttl = 3600  # 1 hour
        self.doc_ttl = 3600  # 1 hour
        self.context_ttl = 1800  # 30 minutes
        
    async def initialize(self) -> None:
        """
        Load embedding model asynchronously.
        Must be called before any retrieval operations.
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
    
    async def encode_query(self, text: str, use_cache: bool = True) -> np.ndarray:
        """
        Encode query text to embedding vector (with cache).
        
        Cache Strategy:
        - Check Redis for cached embedding
        - If miss, compute and store
        - TTL: 1 hour
        
        Args:
            text: Query text to encode
            use_cache: Whether to use cache (default: True)
            
        Returns:
            384-dimensional embedding vector
        """
        if self.model is None:
            raise ValueError("RAG service not initialized. Call initialize() first.")
        
        # Try cache first
        cache_key = cache_service._make_key("embedding", text)
        if use_cache:
            cached = await cache_service.get(cache_key)
            if cached and "embedding" in cached:
                logger.info(f"📦 Using cached embedding for query")
                return np.array(cached["embedding"], dtype=np.float32)
        
        # Compute if not in cache
        try:
            loop = asyncio.get_event_loop()
            embedding = await asyncio.wait_for(
                loop.run_in_executor(None, self.model.encode, text),
                timeout=self.timeout
            )
            
            embedding_array = np.array(embedding, dtype=np.float32)
            
            # Store in cache
            await cache_service.set(
                cache_key,
                {"embedding": embedding_array.tolist()},
                ttl=self.embedding_ttl
            )
            
            return embedding_array
            
        except asyncio.TimeoutError:
            logger.error(f"Encoding timeout for query: {text[:50]}...")
            raise ValueError("Query encoding timeout")
        except Exception as e:
            logger.error(f"Query encoding failed: {e}")
            raise ValueError(f"Query encoding error: {e}")
    
    async def retrieve_documents(
        self,
        session: AsyncSession,
        query_embedding: np.ndarray,
        module_id: Optional[str] = None,
        limit: Optional[int] = None,
        use_cache: bool = True
    ) -> list[dict]:
        """
        Retrieve top-k documents (with cache fallback).
        
        Cache Strategy:
        1. Check Redis for cached results
        2. If miss, query PostgreSQL with pgvector
        3. Store results in Redis
        4. Return documents
        
        Args:
            session: Database session
            query_embedding: Query embedding vector (384-dim numpy array)
            module_id: Optional filter by module
            limit: Override default top_k
            use_cache: Whether to use cache (default: True)
            
        Returns:
            List of documents with similarity scores
        """
        # Create cache key from embedding hash
        embedding_hash = str(hash(query_embedding.tobytes()))
        cache_key = cache_service._make_key(
            f"docs:{module_id or 'all'}",
            embedding_hash
        )
        
        # Try cache first
        if use_cache:
            cached = await cache_service.get(cache_key)
            if cached and "documents" in cached:
                logger.info(f"📦 Using cached documents")
                return cached["documents"]
        
        # Query database if not in cache
        try:
            k = limit or self.top_k
            
            # Convert embedding to string format for SQL
            # pgvector accepts: '[0.1, 0.2, 0.3, ...]'
            embedding_list = query_embedding.tolist()
            embedding_str = str(embedding_list)
            
            # pgvector cosine distance: <=> operator
            # 1 - distance = similarity (0-1 scale)
            query_sql = f"""
                SELECT 
                    chunk_id, 
                    module_id, 
                    content,
                    1 - (embedding <=> '{embedding_str}'::vector) AS similarity
                FROM document_chunks
            """
            
            if module_id:
                query_sql += f" WHERE module_id = '{module_id}'"
            
            query_sql += f" ORDER BY similarity DESC LIMIT {k}"
            
            logger.debug(f"Executing query: {query_sql[:100]}...")
            
            result = await session.execute(text(query_sql))
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
            
            logger.info(
                f"Retrieved {len(documents)}/{k} documents "
                f"(max_similarity={max([d['similarity'] for d in documents] or [0.0]):.3f})"
            )
            
            # Cache results
            await cache_service.set(
                cache_key,
                {"documents": documents},
                ttl=self.doc_ttl
            )
            
            return documents
            
        except Exception as e:
            logger.error(f"Document retrieval failed: {e}")
            logger.error(f"Query was: {query_sql if 'query_sql' in locals() else 'N/A'}")
            raise
    
    async def is_on_topic(
        self,
        query_embedding: np.ndarray,
        max_similarity: float
    ) -> bool:
        """
        Determine if query is on-topic based on similarity threshold.
        
        Args:
            query_embedding: Query embedding
            max_similarity: Maximum similarity score from retrieval
            
        Returns:
            True if on-topic, False otherwise
        """
        is_topic = max_similarity >= self.threshold
        logger.debug(f"On-topic check: {is_topic} (similarity={max_similarity:.3f})")
        return is_topic
    
    async def build_context(
        self,
        session: AsyncSession,
        query: str,
        query_embedding: np.ndarray,
        use_cache: bool = True
    ) -> dict:
        """
        Build complete RAG context (with cache).
        
        Cache Strategy:
        1. Check Redis for full context
        2. If miss, retrieve documents + build context
        3. Cache complete context
        
        Args:
            session: Database session
            query: User query text
            query_embedding: Query embedding
            use_cache: Whether to use cache (default: True)
            
        Returns:
            Dictionary with context, on-topic status, and metadata
        """
        # Try cache first
        cache_key = cache_service._make_key("context", query)
        if use_cache:
            cached = await cache_service.get(cache_key)
            if cached:
                logger.info(f"📦 Using cached context")
                return cached
        
        try:
            # Retrieve documents
            documents = await self.retrieve_documents(
                session,
                query_embedding,
                use_cache=use_cache
            )
            
            max_similarity = max(
                [d["similarity"] for d in documents],
                default=0.0
            )
            
            is_topic = await self.is_on_topic(query_embedding, max_similarity)
            
            # Build context string
            context_parts = []
            for doc in documents:
                context_parts.append(
                    f"[{doc['module_id']}] {doc['content']}"
                )
            
            context = "\n\n".join(context_parts) if context_parts else ""
            
            result = {
                "is_on_topic": is_topic,
                "max_similarity": max_similarity,
                "num_documents": len(documents),
                "documents": documents,
                "context": context,
                "error": None,
                "timestamp": datetime.utcnow().isoformat(),
                "cached": False
            }
            
            # Cache context
            await cache_service.set(
                cache_key,
                result,
                ttl=self.context_ttl
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Context building failed: {e}")
            return {
                "is_on_topic": False,
                "max_similarity": 0.0,
                "num_documents": 0,
                "documents": [],
                "context": "",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
                "cached": False
            }


# Global RAG service instance
rag_service = RAGService()