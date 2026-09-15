import json
import logging
import numpy as np
from sentence_transformers import SentenceTransformer
from pathlib import Path

from config_week2 import (
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    RAG_THRESHOLD,
    RAG_TOP_K,
    EMBEDDINGS_FILE,
    DATA_DIR,
)

logger = logging.getLogger("rag")

# Load embedding model once
embedding_model = SentenceTransformer(EMBEDDING_MODEL)

class RAGRetriever:
    def __init__(self):
        self.embedding_model = embedding_model
        self.chunks = []
        self.embeddings = []
        self.load_embeddings()
    
    def load_embeddings(self):
        """Load pre-computed embeddings from JSON file"""
        if EMBEDDINGS_FILE.exists():
            try:
                with open(EMBEDDINGS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.chunks = data.get('chunks', [])
                    self.embeddings = np.array(data.get('embeddings', []), dtype=np.float32)
                logger.info(f"✅ Loaded {len(self.chunks)} chunks from {EMBEDDINGS_FILE}")
            except Exception as e:
                logger.error(f"Failed to load embeddings: {e}")
                self.chunks = []
                self.embeddings = np.array([], dtype=np.float32)
        else:
            logger.warning(f"Embeddings file not found: {EMBEDDINGS_FILE}")
            logger.info("Run ingest_curriculum.py first to generate embeddings")
    
    async def is_on_topic(self, query: str) -> tuple[bool, float]:
        """
        Check if query is about DNA/biology using embedding similarity.
        
        Returns:
            (is_on_topic: bool, max_similarity: float)
        """
        # Topic anchor sentences for DNA biology
        topic_anchors = [
            "DNA structure and molecular biology",
            "genetics and gene expression",
            "cell biology and heredity",
            "biochemistry of nucleic acids",
            "molecular mechanisms of life",
        ]
        
        try:
            # Embed query and anchors
            query_emb = self.embedding_model.encode([query], convert_to_numpy=True)[0]
            anchor_embs = self.embedding_model.encode(topic_anchors, convert_to_numpy=True)
            
            # Cosine similarity
            query_norm = query_emb / (np.linalg.norm(query_emb) + 1e-8)
            anchor_norms = anchor_embs / (np.linalg.norm(anchor_embs, axis=1, keepdims=True) + 1e-8)
            
            similarities = np.dot(anchor_norms, query_norm)
            max_similarity = float(np.max(similarities))
            is_on_topic = max_similarity >= RAG_THRESHOLD
            
            logger.info(f"Topic check: on_topic={is_on_topic}, max_sim={max_similarity:.3f}")
            return is_on_topic, max_similarity
        
        except Exception as e:
            logger.error(f"Topic check error: {e}")
            return False, 0.0
    
    async def retrieve_top_k(self, query: str, top_k: int = RAG_TOP_K) -> list[dict]:
        """
        Retrieve top-k most similar chunks using cosine similarity.
        
        Returns:
            List of dicts with: content, similarity, topic, chunk_id
        """
        if len(self.chunks) == 0:
            logger.warning("No chunks available for retrieval")
            return []
        
        try:
            # Embed query
            query_emb = self.embedding_model.encode([query], convert_to_numpy=True)[0]
            query_norm = query_emb / (np.linalg.norm(query_emb) + 1e-8)
            
            # Cosine similarity with all chunks
            embedding_norms = self.embeddings / (np.linalg.norm(self.embeddings, axis=1, keepdims=True) + 1e-8)
            similarities = np.dot(embedding_norms, query_norm)
            
            # Get top-k indices
            top_indices = np.argsort(similarities)[-top_k:][::-1]
            
            # Build results
            results = []
            for idx in top_indices:
                if similarities[idx] > 0.0:  # Only include non-zero similarities
                    chunk = self.chunks[int(idx)]
                    results.append({
                        "content": chunk["content"],
                        "topic": chunk.get("topic", "General"),
                        "chunk_id": chunk.get("chunk_id", int(idx)),
                        "similarity": float(similarities[idx])
                    })
            
            logger.info(f"Retrieved {len(results)} chunks. Top similarity: {results[0]['similarity']:.3f if results else 0}")
            return results
        
        except Exception as e:
            logger.error(f"Retrieval error: {e}")
            return []
    
    async def build_rag_context(self, query: str) -> dict:
        """
        Build complete RAG context: topic check + retrieval + formatting.
        
        Returns:
            {
                "is_on_topic": bool,
                "topic_similarity": float,
                "chunks": [list of retrieved chunks],
                "context": "formatted context string",
                "error": "error message if any"
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
                "error": "This question is outside the scope of our DNA biology module. Please ask about DNA structure, replication, transcription, translation, mutations, or related biology topics."
            }
        
        # Step 2: Retrieve chunks
        chunks = await self.retrieve_top_k(query, top_k=RAG_TOP_K)
        
        # Step 3: Format context
        context_lines = ["## DNA Curriculum Context:\n"]
        for i, chunk in enumerate(chunks, 1):
            context_lines.append(f"[Source {i}] Topic: {chunk['topic']} (Relevance: {chunk['similarity']:.1%})")
            context_lines.append(f"{chunk['content']}\n")
        
        context = "\n".join(context_lines) if chunks else ""
        
        return {
            "is_on_topic": True,
            "topic_similarity": topic_sim,
            "chunks": chunks,
            "context": context
        }

# Global RAG instance
_rag_instance = None

def get_rag():
    """Get or create RAG retriever instance"""
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = RAGRetriever()
    return _rag_instance
