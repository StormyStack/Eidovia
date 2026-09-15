import os
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
EMBEDDINGS_FILE = DATA_DIR / "embeddings.json"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

# Sentence Transformers
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

# RAG Configuration
RAG_THRESHOLD = 0.35  # Cosine similarity threshold for on-topic detection
RAG_TOP_K = 3  # Number of chunks to retrieve

# API
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8001"))

# LLM Configuration
USE_MOCK_LLM = True  # Week 2: mock, later swap to real Phi-3

# Mock LLM responses (by topic)
MOCK_RESPONSES = {
    "structure": "DNA (deoxyribonucleic acid) is a double helix molecule made of nucleotides. Each nucleotide contains a sugar (deoxyribose), a phosphate group, and a nitrogenous base (A, T, G, or C). The two strands are held together by hydrogen bonds between complementary base pairs: adenine pairs with thymine, and guanine pairs with cytosine.",
    
    "replication": "DNA replication is a semi-conservative process where the double helix unwinds and each strand serves as a template for a new complementary strand. DNA polymerase catalyzes the formation of phosphodiester bonds between nucleotides. The leading strand is synthesized continuously, while the lagging strand is synthesized in short Okazaki fragments that are later joined by DNA ligase.",
    
    "transcription": "Transcription is the process where RNA polymerase reads the DNA template strand and synthesizes a complementary RNA molecule (mRNA). In eukaryotes, the mRNA undergoes processing: 5' capping, 3' polyadenylation, and splicing to remove introns. The mature mRNA then carries genetic information to the ribosome for protein synthesis.",
    
    "translation": "Translation is the process where ribosomes decode mRNA to synthesize proteins. Transfer RNA (tRNA) molecules bring amino acids to the ribosome, matching their anticodons to mRNA codons. The ribosome catalyzes peptide bond formation between amino acids, creating the polypeptide chain that becomes a functional protein.",
    
    "mutation": "Mutations are changes in DNA sequence that can result from replication errors, environmental damage, or spontaneous changes. Point mutations affect single nucleotides and can be silent, missense, or nonsense mutations. Larger mutations include insertions, deletions, and inversions. While most mutations are neutral or harmful, some can be beneficial and drive evolution.",
    
    "default": "Based on our DNA curriculum, this topic relates to molecular biology and genetics. The answer involves the central dogma of molecular biology: DNA replication, transcription to RNA, and translation to proteins. These processes are fundamental to all living organisms.",
}
