"""
DNA quiz content (source: DNA_MCQ_Quiz.pdf — 20 questions: 6 easy, 8 medium, 6 hard).

This file is the definition of quiz version 1. On startup the gateway stores it in quiz_versions
(questions and answer key in separate columns). The answer key never leaves the server before an
attempt is submitted. Changing a question or an answer means a NEW version number, so old attempts
keep pointing at the exact questions they were scored against.
"""

QUIZ_ID = "dna"
QUIZ_VERSION = 1
QUIZ_TITLE = "DNA Multiple-Choice Quiz"
TIME_LIMIT_S = 30 * 60          # an attempt must be submitted within 30 minutes of starting
COOLDOWN_HOURS = 12             # one attempt every 12 hours (counted from the start of the last attempt)
FORCE_COST = 3                  # wildcards for a Force Attempt during the cooldown
OPTION_KEYS = ("A", "B", "C", "D")

# (level, question, (A, B, C, D), answer, explanation)
_QUESTIONS = [
    ("easy", "Which set lists the four nitrogenous bases found in DNA?",
     ("A, U, G, C", "A, T, G, C", "A, T, G, U", "T, U, C, G"), "B",
     "DNA uses adenine, thymine, guanine and cytosine. Uracil is found in RNA."),
    ("easy", "In DNA, adenine pairs with which base?",
     ("Thymine", "Guanine", "Cytosine", "Uracil"), "A",
     "A pairs with T through two hydrogen bonds. G pairs with C."),
    ("easy", "How many hydrogen bonds form between an A-T base pair?",
     ("One", "Two", "Three", "Four"), "B",
     "A-T has two hydrogen bonds. G-C has three."),
    ("easy", "The sugar in the DNA backbone is:",
     ("Ribose", "Deoxyribose", "Glucose", "Fructose"), "B",
     "Deoxyribose lacks an oxygen on the 2' carbon, which is where the name comes from."),
    ("easy", "In a eukaryotic cell, most of the genomic DNA is located in the:",
     ("Mitochondria", "Ribosome", "Nucleus", "Cytoplasm"), "C",
     "Nuclear DNA is the bulk of the genome. Mitochondria carry a small separate genome."),
    ("easy", "Which enzyme unwinds the double helix at the replication fork?",
     ("DNA polymerase", "Helicase", "DNA ligase", "Primase"), "B",
     "Helicase breaks the hydrogen bonds between base pairs."),
    ("medium", "DNA polymerase adds nucleotides in which direction?",
     ("3' to 5'", "5' to 3'", "In both directions", "Direction depends on the strand"), "B",
     "New DNA is always synthesized 5' to 3', adding to the free 3'-OH end."),
    ("medium", "Okazaki fragments are formed on which strand during replication?",
     ("Leading strand", "Lagging strand", "Both strands equally", "Neither strand"), "B",
     "The lagging strand is synthesized discontinuously in short fragments because it runs opposite to the fork direction."),
    ("medium", "Which enzyme joins Okazaki fragments into a continuous strand?",
     ("Helicase", "Primase", "DNA ligase", "Topoisomerase"), "C",
     "Ligase seals the nicks by forming phosphodiester bonds."),
    ("medium", "What is the role of primase?",
     ("Unwinding the helix", "Synthesizing a short RNA primer", "Proofreading new bases", "Sealing nicks"), "B",
     "DNA polymerase cannot start a strand without a primer that provides a 3'-OH group."),
    ("medium", "RNA polymerase II synthesizes which product in eukaryotes?",
     ("rRNA", "mRNA", "tRNA", "DNA"), "B",
     "RNA polymerase II transcribes protein-coding genes and most snRNAs and miRNAs; tRNA is made by RNA polymerase III."),
    ("medium", "Which DNA element is the binding site for the transcription machinery?",
     ("Enhancer", "Promoter", "Intron", "3' untranslated region"), "B",
     "The promoter, including elements such as the TATA box, is where RNA polymerase and transcription factors assemble."),
    ("medium", "The start codon AUG codes for which amino acid?",
     ("Serine", "Tryptophan", "Methionine", "Stop"), "C",
     "AUG specifies methionine, and in eukaryotes it marks the start of translation."),
    ("medium", "Which of the following is NOT a stop codon?",
     ("UAA", "UAG", "UGA", "UUA"), "D",
     "UUA codes for leucine. The stop codons are UAA, UAG and UGA."),
    ("hard", "A mutation changes codon GAA to GAG. Both codons specify glutamate. This is best classified as a:",
     ("Frameshift mutation", "Nonsense mutation", "Silent mutation", "Missense mutation"), "C",
     "The amino acid is unchanged, so the mutation is silent. Missense changes the amino acid; nonsense creates a stop codon."),
    ("hard", "Thymine dimers caused by UV light are removed mainly by which repair pathway?",
     ("Base excision repair", "Nucleotide excision repair", "Mismatch repair", "Non-homologous end joining"), "B",
     "NER removes bulky distortions such as thymine dimers. BER handles single damaged bases."),
    ("hard", "In double-stranded DNA, if adenine makes up 30% of the bases, what percentage is guanine?",
     ("20%", "30%", "40%", "70%"), "A",
     "Chargaff's rules give A = T = 30%, so G + C = 40%, and G = C = 20%."),
    ("hard", "DNA methylation at CpG islands in a gene promoter is generally associated with:",
     ("Gene activation", "Gene silencing", "Replication initiation", "Splicing of pre-mRNA"), "B",
     "Promoter methylation typically recruits proteins that compact chromatin and reduce transcription."),
    ("hard", "What does topoisomerase do during DNA replication?",
     ("Synthesizes RNA primers", "Relieves torsional strain by cutting and rejoining DNA strands",
      "Adds telomere repeats", "Proofreads the new strand"), "B",
     "Topoisomerases relieve positive supercoils ahead of the fork by temporarily breaking and rejoining the backbone."),
    ("hard", "Why can conventional DNA polymerase not fully replicate the ends of a linear chromosome?",
     ("The template is too short to read",
      "After the RNA primer at the 5' end is removed, there is no upstream 3'-OH to fill the gap",
      "Ligase cannot join the last fragment", "Helicase cannot reach the telomere"), "B",
     "This is the end-replication problem. Telomerase solves it by extending the 3' overhang with its own RNA template."),
]

# What the client may see (no answers)
QUESTIONS = [
    {"id": str(i), "level": level, "text": text,
     "options": [{"key": k, "text": t} for k, t in zip(OPTION_KEYS, options)]}
    for i, (level, text, options, _answer, _why) in enumerate(_QUESTIONS, start=1)
]
# Server only
ANSWER_KEY = {
    str(i): {"answer": answer, "explanation": why}
    for i, (_level, _text, _options, answer, why) in enumerate(_QUESTIONS, start=1)
}

assert len(QUESTIONS) == 20 and all(a["answer"] in OPTION_KEYS for a in ANSWER_KEY.values())
