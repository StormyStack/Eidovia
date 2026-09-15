#!/usr/bin/env python3
"""Week 2 Simplified Ingestion - Memory Efficient"""

import json
import logging
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingest")

# Smaller, faster model
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# Simple chunks (manually curated key concepts)
CHUNKS = [
    {"topic": "DNA Structure", "content": "DNA is a double helix molecule made of nucleotides. Each nucleotide has deoxyribose sugar, phosphate group, and nitrogenous base (A,T,G,C). Adenine pairs with thymine, guanine pairs with cytosine."},
    {"topic": "DNA Structure", "content": "The double helix has two antiparallel strands held together by hydrogen bonds between complementary base pairs. This structure was discovered by Watson, Crick, Franklin, and Wilkins in 1953."},
    {"topic": "DNA Replication", "content": "DNA replication is semi-conservative: each strand serves as template for a new strand. DNA polymerase catalyzes bond formation. Leading strand synthesized continuously, lagging strand in Okazaki fragments."},
    {"topic": "DNA Replication", "content": "DNA polymerase requires primer and synthesizes 5' to 3'. Helicase unwinds helix, primase makes RNA primer, ligase joins fragments. Rate: ~50 nucleotides/second in prokaryotes."},
    {"topic": "Transcription", "content": "Transcription: RNA polymerase reads DNA template, synthesizes complementary RNA (mRNA). In eukaryotes: 5' capping, 3' polyadenylation, splicing (removes introns, joins exons)."},
    {"topic": "Translation", "content": "Translation: ribosomes decode mRNA. tRNA brings amino acids, anticodon matches codon. Ribosome catalyzes peptide bonds. Start codon AUG, stop codons UAA/UAG/UGA."},
    {"topic": "Mutations", "content": "Mutations: changes in DNA sequence. Point mutations (substitution), insertions, deletions, frameshifts. Most neutral or harmful, some beneficial. Drive evolution through natural selection."},
    {"topic": "Gene Regulation", "content": "Transcription factors bind promoters/enhancers to regulate RNA polymerase. Chromatin structure affects accessibility. DNA methylation silences genes, histone modifications activate/repress transcription."},
    {"topic": "Central Dogma", "content": "Central Dogma: DNA → RNA → Protein. Replication copies DNA, transcription makes RNA, translation makes protein. Foundation of molecular biology."},
    {"topic": "Nucleotides", "content": "Nucleotides: sugar (deoxyribose) + phosphate + base. Purines: adenine (A), guanine (G). Pyrimidines: thymine (T), cytosine (C). Connected by phosphodiester bonds."},
]

def ingest():
    """Generate embeddings for key DNA concepts"""
    logger.info("=" * 60)
    logger.info("📖 WEEK 2: SIMPLIFIED DNA CURRICULUM INGESTION")
    logger.info("=" * 60)
    
    logger.info(f"\nProcessing {len(CHUNKS)} key concept chunks...")
    
    embeddings_list = []
    for i, chunk in enumerate(CHUNKS):
        embedding = embedding_model.encode([chunk["content"]], convert_to_numpy=True)[0]
        embeddings_list.append(embedding.astype('float32').tolist())
        logger.info(f"  [{i+1}/{len(CHUNKS)}] {chunk['topic']}")
    
    # Save
    output_data = {
        "model": "all-MiniLM-L6-v2",
        "dimension": 384,
        "chunk_count": len(CHUNKS),
        "chunks": CHUNKS,
        "embeddings": embeddings_list
    }
    
    with open("data/embeddings.json", 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2)
    
    logger.info(f"\n✅ COMPLETE")
    logger.info(f"Chunks: {len(CHUNKS)}")
    logger.info(f"Saved: data/embeddings.json")
    logger.info("=" * 60 + "\n")

if __name__ == "__main__":
    ingest()