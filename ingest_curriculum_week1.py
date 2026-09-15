#!/usr/bin/env python3
"""
Ingestion script: Load DNA curriculum into PostgreSQL with pgvector embeddings.
Run this AFTER Docker containers are running.

Usage:
    python ingest_curriculum.py
"""

import asyncio
import asyncpg
import logging
from sentence_transformers import SentenceTransformer
import re

from config import DATABASE_ASYNC_URL, EMBEDDING_MODEL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingest")

# Load embedding model
embedding_model = SentenceTransformer(EMBEDDING_MODEL)

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """
    Split text into overlapping chunks for better context retention.
    
    Args:
        text: Raw text to chunk
        chunk_size: Target chunk size in characters
        overlap: Overlap between chunks
    
    Returns:
        List of text chunks
    """
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk.strip())
        start = end - overlap
    
    return [c for c in chunks if len(c.strip()) > 50]  # Filter empty chunks

def extract_sections(curriculum_text: str) -> list[dict]:
    """
    Parse curriculum into structured sections.
    
    Returns:
        List of sections with topic, content, and chunk info
    """
    sections = []
    
    # Split by major sections (## SECTION)
    raw_sections = re.split(r'## SECTION \d+:', curriculum_text)
    
    section_topics = [
        "DNA STRUCTURE AND MOLECULAR COMPOSITION",
        "DNA REPLICATION",
        "GENE EXPRESSION - TRANSCRIPTION AND TRANSLATION",
        "MUTATIONS AND GENETIC VARIATION",
        "GENE REGULATION AND EPIGENETICS"
    ]
    
    for i, section_content in enumerate(raw_sections[1:]):  # Skip preamble
        topic = section_topics[i] if i < len(section_topics) else "General DNA Biology"
        
        # Clean section content
        section_text = section_content.strip()
        
        # Create section record
        sections.append({
            "topic": topic,
            "content": section_text
        })
    
    return sections

async def ingest_curriculum(filepath: str = "dna_curriculum.txt"):
    """
    Main ingestion function: Read curriculum, chunk, embed, and store.
    
    Args:
        filepath: Path to curriculum text file
    """
    logger.info(f"📖 Starting curriculum ingestion from {filepath}...")
    
    # Read curriculum
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            curriculum_text = f.read()
        logger.info(f"✅ Curriculum loaded ({len(curriculum_text)} chars)")
    except FileNotFoundError:
        logger.error(f"❌ Curriculum file not found: {filepath}")
        return
    
    # Parse sections
    sections = extract_sections(curriculum_text)
    logger.info(f"✅ Parsed {len(sections)} sections")
    
    # Connect to database
    conn = await asyncpg.connect(DATABASE_ASYNC_URL)
    
    try:
        # Clear existing chunks (optional)
        await conn.execute("DELETE FROM document_chunks;")
        logger.info("✅ Cleared existing chunks")
        
        # Process each section
        total_chunks = 0
        for section_idx, section in enumerate(sections):
            topic = section["topic"]
            content = section["content"]
            
            # Chunk the section
            chunks = chunk_text(content, chunk_size=600, overlap=150)
            logger.info(f"  Topic '{topic}': {len(chunks)} chunks")
            
            # Embed and store chunks
            for chunk_idx, chunk in enumerate(chunks):
                # Generate embedding
                embedding = embedding_model.encode([chunk], convert_to_numpy=True)[0]
                embedding_list = embedding.astype('float32').tolist()
                
                # Insert into database
                try:
                    await conn.execute("""
                        INSERT INTO document_chunks 
                        (doc_id, chunk_index, content, embedding, topic)
                        VALUES ($1, $2, $3, $4, $5)
                    """,
                    f"section_{section_idx:02d}",
                    chunk_idx,
                    chunk,
                    embedding_list,
                    topic
                    )
                    total_chunks += 1
                except Exception as e:
                    logger.error(f"Failed to insert chunk: {e}")
        
        logger.info(f"✅ Successfully inserted {total_chunks} chunks into database")
        
        # Verify ingestion
        count = await conn.fetchval("SELECT COUNT(*) FROM document_chunks;")
        logger.info(f"📊 Final count: {count} chunks in document_chunks table")
        
    except Exception as e:
        logger.error(f"❌ Ingestion failed: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(ingest_curriculum())
