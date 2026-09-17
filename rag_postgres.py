#!/usr/bin/env python3
"""
RAG Retrieval Pipeline - PostgreSQL + Python Vector Search
Uses NumPy for cosine similarity (no pgvector needed)
"""

import numpy as np
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class RAGRetriever:
    """RAG system using PostgreSQL document chunks + Python similarity search"""
    
    def __init__(self, db, threshold: float = 0.40, top_k: int = 3):
        self.db = db
        self.threshold = threshold
        self.top_k = top_k
        self.chunks = []
        self.embeddings = []
    
    async def load_chunks(self):
        """Load curriculum chunks from PostgreSQL"""
        try:
            chunks = await self.db.get_document_chunks()
            self.chunks = [
                {
                    'chunk_id': str(chunk.chunk_id),
                    'module_id': chunk.module_id,
                    'content': chunk.chunk_text,
                    'embedding': np.array(chunk.embedding) if chunk.embedding else None
                }
                for chunk in chunks
            ]
            self.embeddings = [c['embedding'] for c in self.chunks if c['embedding'] is not None]
            logger.info(f"✅ Loaded {len(self.chunks)} chunks from PostgreSQL")
            return len(self.chunks) > 0
        except Exception as e:
            logger.error(f"Failed to load chunks: {e}")
            return False
    
    async def is_on_topic(self, query_embedding: np.ndarray) -> tuple:
        """Check if query is on-topic using topic anchors"""
        topic_anchors = [
            "DNA structure molecular biology",
            "genetics gene expression",
            "cell biology heredity",
            "biochemistry nucleic acids",
            "molecular mechanisms life"
        ]
        
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer('all-MiniLM-L6-v2')
            
            anchor_embeddings = model.encode(topic_anchors, convert_to_numpy=True)
            query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)
            anchor_norms = anchor_embeddings / (np.linalg.norm(anchor_embeddings, axis=1, keepdims=True) + 1e-8)
            
            similarities = np.dot(anchor_norms, query_norm)
            max_similarity = float(np.max(similarities))
            is_on_topic = max_similarity >= self.threshold
            
            logger.info(f"Topic check: on_topic={is_on_topic}, similarity={max_similarity:.3f}")
            return is_on_topic, max_similarity
        except Exception as e:
            logger.error(f"Topic check error: {e}")
            return False, 0.0
    
    async def retrieve_top_k(self, query_embedding: np.ndarray) -> List[Dict]:
        """Retrieve top-k most similar chunks using cosine similarity"""
        if len(self.embeddings) == 0:
            logger.warning("No embeddings available")
            return []
        
        try:
            embeddings_array = np.array(self.embeddings)
            query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)
            embedding_norms = embeddings_array / (np.linalg.norm(embeddings_array, axis=1, keepdims=True) + 1e-8)
            
            similarities = np.dot(embedding_norms, query_norm)
            top_indices = np.argsort(similarities)[-self.top_k:][::-1]
            
            results = []
            for idx in top_indices:
                if similarities[idx] > 0.0:
                    chunk = self.chunks[idx]
                    results.append({
                        'chunk_id': chunk['chunk_id'],
                        'module_id': chunk['module_id'],
                        'content': chunk['content'],
                        'similarity': float(similarities[idx])
                    })
            
            logger.info(f"Retrieved {len(results)} chunks. Top similarity: {results[0]['similarity']:.3f if results else 0}")
            return results
        except Exception as e:
            logger.error(f"Retrieval error: {e}")
            return []
    
    async def build_context(self, query: str, query_embedding: np.ndarray = None) -> Dict:
        """Build RAG context: topic check + retrieval + formatting"""
        
        # Generate embedding if not provided
        if query_embedding is None:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer('all-MiniLM-L6-v2')
            query_embedding = model.encode([query], convert_to_numpy=True)[0]
        
        # Step 1: Topic check
        is_on_topic, topic_sim = await self.is_on_topic(query_embedding)
        
        if not is_on_topic:
            return {
                "is_on_topic": False,
                "topic_similarity": topic_sim,
                "chunks": [],
                "context": "",
                "error": "This question is outside the scope of our DNA biology module."
            }
        
        # Step 2: Retrieve chunks
        chunks = await self.retrieve_top_k(query_embedding)
        
        # Step 3: Format context
        context_lines = ["## DNA Curriculum Context:\n"]
        for i, chunk in enumerate(chunks, 1):
            context_lines.append(f"[Source {i}] Module: {chunk['module_id']} (Relevance: {chunk['similarity']:.1%})")
            context_lines.append(f"{chunk['content']}\n")
        
        context = "\n".join(context_lines) if chunks else ""
        
        return {
            "is_on_topic": True,
            "topic_similarity": topic_sim,
            "chunks": chunks,
            "context": context
        }

# Global RAG instance
rag = None

async def get_rag():
    """Get or create RAG instance"""
    global rag
    if rag is None:
        rag = RAGRetriever(db=None)  # Initialize with db later
    return rag
