import asyncpg
import numpy as np
import logging
from sentence_transformers import SentenceTransformer
from config import (
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    RAG_THRESHOLD,
    RAG_TOP_K,
    DATABASE_ASYNC_URL
)

logger = logging.getLogger("rag")

# Load embedding model once (reuse across requests)
embedding_model = SentenceTransformer(EMBEDDING_MODEL)

class RAGRetriever:
    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.embedding_model = embedding_model
    
    async def retrieve_top_k(self, query: str, top_k: int = RAG_TOP_K) -> list[dict]:
        """
        Retrieve top-k most similar document chunks using cosine similarity.
        
        Args:
            query: User question/query
            top_k: Number of chunks to retrieve
        
        Returns:
            List of chunks with similarity scores
        """
        # Embed the query
        query_embedding = self.embedding_model.encode([query], convert_to_numpy=True)[0]
        query_embedding = query_embedding.astype(np.float32).tolist()
        
        # Query PostgreSQL with pgvector cosine similarity
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    id,
                    doc_id,
                    chunk_index,
                    content,
                    topic,
                    (1 - (embedding <=> $1::vector)) AS similarity
                FROM document_chunks
                ORDER BY similarity DESC
                LIMIT $2;
            """, query_embedding, top_k)
        
        chunks = []
        for row in rows:
            chunks.append({
                "id": row["id"],
                "doc_id": row["doc_id"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "topic": row["topic"],
                "similarity": float(row["similarity"])
            })
        
        logger.info(f"Retrieved {len(chunks)} chunks. Top similarity: {chunks[0]['similarity']:.3f if chunks else 0}")
        return chunks
    
    async def is_on_topic(self, query: str, threshold: float = RAG_THRESHOLD) -> tuple[bool, float]:
        """
        Fast topic check using embedding similarity against topic anchors.
        
        Args:
            query: User question
            threshold: Minimum similarity to consider on-topic
        
        Returns:
            (is_on_topic: bool, max_similarity: float)
        """
        # Topic anchor sentences for DNA biology
        topic_anchors = [
            "DNA structure and function",
            "DNA replication and genetic information",
            "Nucleotides and base pairing",
            "Cell biology and molecular genetics",
            "DNA mutation and variation",
        ]
        
        # Embed query and anchors
        query_emb = self.embedding_model.encode([query], convert_to_numpy=True)[0]
        anchor_embs = self.embedding_model.encode(topic_anchors, convert_to_numpy=True)
        
        # Compute cosine similarities
        similarities = np.dot(anchor_embs, query_emb) / (
            np.linalg.norm(anchor_embs, axis=1) * np.linalg.norm(query_emb)
        )
        
        max_similarity = float(np.max(similarities))
        is_on_topic = max_similarity >= threshold
        
        logger.info(f"Topic check: on_topic={is_on_topic}, max_sim={max_similarity:.3f}")
        return is_on_topic, max_similarity
    
    async def build_rag_context(self, query: str) -> dict:
        """
        Build complete RAG context: topic check + retrieval.
        
        Returns:
            {
                "is_on_topic": bool,
                "topic_similarity": float,
                "chunks": [list of retrieved chunks],
                "context": "formatted context string"
            }
        """
        # Step 1: Topic check
        is_on_topic, topic_sim = await self.is_on_topic(query)
        
        if not is_on_topic:
            logger.warning(f"Query rejected: off-topic (similarity={topic_sim:.3f})")
            return {
                "is_on_topic": False,
                "topic_similarity": topic_sim,
                "chunks": [],
                "context": "",
                "error": "This question is outside the scope of our DNA biology module."
            }
        
        # Step 2: Retrieve chunks
        chunks = await self.retrieve_top_k(query, top_k=RAG_TOP_K)
        
        # Step 3: Format context
        context_lines = ["## Retrieved Context from DNA Curriculum:\n"]
        for i, chunk in enumerate(chunks, 1):
            context_lines.append(f"[{i}] (Topic: {chunk['topic']}, Similarity: {chunk['similarity']:.2%})")
            context_lines.append(f"{chunk['content']}\n")
        
        context = "\n".join(context_lines)
        
        return {
            "is_on_topic": True,
            "topic_similarity": topic_sim,
            "chunks": chunks,
            "context": context
        }

async def init_rag(db_pool):
    """Initialize RAG retriever"""
    logger.info(f"Initializing RAG with model: {EMBEDDING_MODEL}")
    return RAGRetriever(db_pool)
