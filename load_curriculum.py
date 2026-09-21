#!/usr/bin/env python3
"""
Load DNA Curriculum into PostgreSQL
Populate document_chunks table with embeddings
"""

import asyncio
import logging
import numpy as np
from sentence_transformers import SentenceTransformer
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from database_postgres import Database
from models_postgres import DocumentChunk, Module, Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("load_curriculum")

# DNA Curriculum Content
DNA_CURRICULUM = [
    {
        "topic": "DNA Structure",
        "source_doc": "molecular_biology_101.txt",
        "content": """
        DNA (deoxyribonucleic acid) is a molecule that carries genetic instructions. 
        It consists of two strands wound around each other in a double helix. 
        Each strand is made of nucleotides: adenine (A), thymine (T), guanine (G), and cytosine (C).
        Base pairing follows specific rules: A pairs with T, G pairs with C.
        This complementary base pairing is essential for DNA replication and stability.
        """,
        "module_id": "dna-01"
    },
    {
        "topic": "DNA Replication",
        "source_doc": "molecular_biology_201.txt",
        "content": """
        DNA replication is the process by which a DNA molecule makes a copy of itself.
        It occurs during the S phase of the cell cycle and is semi-conservative.
        DNA helicase unwinds the double helix, breaking hydrogen bonds between base pairs.
        DNA polymerase reads the template strand and synthesizes a new complementary strand.
        Primers are laid down by primase to provide a 3'-OH group for synthesis.
        The result is two identical DNA molecules, each with one original and one new strand.
        """,
        "module_id": "dna-02"
    },
    {
        "topic": "Transcription",
        "source_doc": "gene_expression_101.txt",
        "content": """
        Transcription is the process of copying genetic information from DNA to messenger RNA (mRNA).
        RNA polymerase binds to the promoter region and unwinds the DNA double helix.
        Only one strand (template strand) is used as the template for RNA synthesis.
        RNA nucleotides (A, U, G, C) are added one at a time by complementary base pairing.
        The resulting mRNA carries genetic instructions from the nucleus to ribosomes.
        Transcription occurs in the nucleus of eukaryotic cells.
        """,
        "module_id": "dna-03"
    },
    {
        "topic": "Translation",
        "source_doc": "protein_synthesis_101.txt",
        "content": """
        Translation is the process by which mRNA instructions are converted into proteins.
        Ribosomes read mRNA codons (3-nucleotide sequences) and match them to transfer RNA (tRNA).
        Each tRNA carries a specific amino acid. A codon specifies which amino acid to add.
        The ribosome catalyzes peptide bonds between amino acids, forming a polypeptide chain.
        Translation begins at the start codon (AUG) and ends at stop codons (UAA, UAG, UGA).
        The resulting protein folds into its functional 3D structure.
        """,
        "module_id": "dna-04"
    },
    {
        "topic": "Genetic Mutations",
        "source_doc": "genetics_mutations.txt",
        "content": """
        Mutations are changes in DNA sequences. They can occur spontaneously or be induced.
        Point mutations change a single nucleotide: substitution, insertion, or deletion.
        Silent mutations do not change the amino acid (due to redundancy in the genetic code).
        Missense mutations change the amino acid, potentially affecting protein function.
        Nonsense mutations create a premature stop codon, truncating the protein.
        Frameshift mutations shift the reading frame, drastically altering all downstream codons.
        Most mutations are neutral or harmful, but some can provide evolutionary advantages.
        """,
        "module_id": "dna-05"
    },
    {
        "topic": "Gene Expression Regulation",
        "source_doc": "gene_regulation.txt",
        "content": """
        Gene expression can be regulated at multiple levels: transcriptional, post-transcriptional, and translational.
        Transcriptional regulation involves promoters, enhancers, and repressors controlling RNA polymerase activity.
        Chromatin structure affects gene accessibility: euchromatin (open) vs heterochromatin (closed).
        Post-transcriptional regulation includes alternative splicing, creating multiple proteins from one gene.
        The lac operon is a classic example of prokaryotic gene regulation in response to lactose.
        Epigenetic modifications (DNA methylation, histone acetylation) affect gene silencing without DNA changes.
        """,
        "module_id": "dna-06"
    },
    {
        "topic": "DNA Repair Mechanisms",
        "source_doc": "dna_maintenance.txt",
        "content": """
        DNA is constantly exposed to damaging agents: UV radiation, chemicals, and spontaneous errors.
        Mismatch repair corrects errors made by DNA polymerase (wrong base paired).
        Excision repair removes damaged nucleotides and replaces them with correct ones.
        Base excision repair specifically targets damaged bases like uracil in DNA.
        Nucleotide excision repair removes larger regions of damaged DNA (e.g., UV-induced thymine dimers).
        Double-strand breaks are repaired by non-homologous end joining (NHEJ) or homologous recombination (HR).
        Without proper DNA repair, mutations accumulate, potentially leading to cancer.
        """,
        "module_id": "dna-07"
    },
    {
        "topic": "Inheritance Patterns",
        "source_doc": "mendelian_genetics.txt",
        "content": """
        Inheritance patterns describe how traits pass from parents to offspring.
        Gregor Mendel discovered basic inheritance rules using pea plants.
        Dominant traits are expressed when at least one dominant allele is present (heterozygous or homozygous).
        Recessive traits require two recessive alleles to be expressed (homozygous recessive).
        The Punnett square predicts offspring genotype and phenotype ratios.
        Incomplete dominance results in intermediate phenotypes in heterozygotes.
        Codominance allows both alleles to be expressed simultaneously (e.g., AB blood type).
        Sex-linked inheritance occurs on X or Y chromosomes, affecting inheritance patterns differently.
        """,
        "module_id": "dna-08"
    },
    {
        "topic": "Molecular Cloning",
        "source_doc": "biotechnology_basics.txt",
        "content": """
        Molecular cloning is the technique of creating identical copies of DNA sequences.
        Restriction enzymes (restriction endonucleases) cut DNA at specific recognition sites.
        DNA ligase joins DNA fragments by forming phosphodiester bonds.
        Vectors (plasmids or viruses) carry foreign DNA into host cells for replication.
        Bacterial plasmids are small, circular DNA molecules used as cloning vectors.
        Recombinant DNA is created by combining DNA from different sources.
        PCR (Polymerase Chain Reaction) amplifies specific DNA sequences exponentially through repeated cycles.
        DNA sequencing determines the order of nucleotides in a DNA molecule.
        """,
        "module_id": "dna-09"
    },
    {
        "topic": "Evolution and Natural Selection",
        "source_doc": "evolution_genetics.txt",
        "content": """
        DNA mutations provide genetic variation within populations.
        Natural selection acts on this variation: beneficial traits increase, harmful ones decrease.
        Genetic drift causes random changes in allele frequency, especially in small populations.
        Gene flow introduces new alleles when individuals migrate between populations.
        Hardy-Weinberg equilibrium describes populations with no evolution occurring.
        Speciation occurs when populations accumulate enough differences to become reproductively isolated.
        Molecular clocks estimate divergence times between species using DNA sequence differences.
        Evidence for evolution includes fossil records, anatomical homologies, and DNA comparisons.
        """,
        "module_id": "dna-10"
    }
]

async def load_curriculum():
    """Load DNA curriculum into PostgreSQL"""
    
    db = Database()
    await db.connect()
    
    logger.info("=" * 70)
    logger.info("📚 LOADING DNA CURRICULUM INTO POSTGRESQL")
    logger.info("=" * 70)
    
    try:
        # Initialize SentenceTransformer for embeddings
        logger.info("Loading sentence-transformers model...")
        model = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info(f"✅ Model loaded: all-MiniLM-L6-v2 (384-dim embeddings)")
        
        # Get async session
        async with db.async_session_maker() as session:
            
            # Create modules first
            modules_created = 0
            for chunk_data in DNA_CURRICULUM:
                module_id = chunk_data["module_id"]
                
                # Check if module exists
                from sqlalchemy import select
                result = await session.execute(
                    select(Module).where(Module.module_id == module_id)
                )
                if not result.scalars().first():
                    module = Module(
                        module_id=module_id,
                        name=chunk_data["topic"],
                        scene_name=f"Scene_{chunk_data['topic'].replace(' ', '_')}",
                        cdn_bundle_url=f"https://cdn.example.com/{module_id}.bundle",
                        difficulty=1
                    )
                    session.add(module)
                    modules_created += 1
            
            if modules_created > 0:
                await session.commit()
                logger.info(f"✅ Created {modules_created} modules")
            
            # Load chunks with embeddings
            chunks_loaded = 0
            for chunk_data in DNA_CURRICULUM:
                try:
                    # Generate embedding
                    embedding = model.encode([chunk_data["content"]], convert_to_numpy=True)[0]
                    embedding_list = embedding.tolist()
                    
                    # Create chunk
                    chunk = DocumentChunk(
                        chunk_id=uuid.uuid4(),
                        module_id=chunk_data["module_id"],
                        source_doc=chunk_data["source_doc"],
                        chunk_text=chunk_data["content"].strip(),
                        embedding=embedding_list
                    )
                    session.add(chunk)
                    chunks_loaded += 1
                    
                    logger.info(f"  ✅ {chunk_data['topic']:30} | Embedding: {len(embedding_list)}-dim | Module: {chunk_data['module_id']}")
                
                except Exception as e:
                    logger.error(f"Error loading chunk {chunk_data['topic']}: {e}")
            
            # Commit all chunks
            await session.commit()
            
            logger.info("")
            logger.info("=" * 70)
            logger.info(f"✅ CURRICULUM LOADED")
            logger.info(f"   Chunks loaded: {chunks_loaded}")
            logger.info(f"   Modules created: {modules_created}")
            logger.info(f"   Embedding dimension: 384 (all-MiniLM-L6-v2)")
            logger.info("=" * 70)
            
            # Verify
            result = await session.execute(
                select(DocumentChunk)
            )
            total_chunks = len(result.scalars().all())
            logger.info(f"✅ Verification: {total_chunks} total chunks in database")
    
    except Exception as e:
        logger.error(f"Failed to load curriculum: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(load_curriculum())
