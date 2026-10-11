"""
HOE evaluation: does the gold sub-section appear in the top 3 at each depth cap?

Run from services/ai with the AI service on localhost:8001:
    E:\\Thesis\\.venv\\Scripts\\python.exe -m scripts.eval_hoe

Writes eval_results.csv next to this folder's parent (services/ai/).
"""

import csv
from pathlib import Path

import httpx

API = "http://localhost:8001/api/chat"
OUT = Path(__file__).resolve().parent.parent / "eval_results.csv"
CAPS = ["flat", 1, 2, 3, 4]  # "flat" = no depth cap

# (question, gold sub-section title, target HOE level for that question)
QUESTIONS = [
    ("What shape does DNA have?", "The Double Helix Structure (NCBI)", 1),
    ("Which base pairs with adenine?", "Base Pairing and Chargaff's Rules", 2),
    ("What are the parts of a nucleotide?", "Nucleotide Structure (OpenStax Biology)", 3),
    ("Why does DNA separate into two strands during replication?",
     "Semi-Conservative Replication (OpenStax Biology)", 4),
    ("Which enzyme builds new DNA strands?", "DNA Polymerase and Enzyme Catalysis (NCBI)", 4),
    ("Why is one DNA strand made in short pieces?", "Leading and Lagging Strands (Khan Academy)", 4),
    ("What is the 5' cap on mRNA?", "mRNA Processing in Eukaryotes (NCBI)", 4),
    ("How does the ribosome read mRNA?", "Translation Process (Khan Academy)", 4),
    ("What is a frameshift mutation?", "Types of Mutations (OpenStax Biology)", 3),
    ("What does DNA methylation do?", "DNA Methylation (NCBI)", 4),
]


def run():
    rows = []
    with httpx.Client(timeout=300) as client:
        for question, gold, target in QUESTIONS:
            for cap in CAPS:
                body = {"question": question}
                if cap != "flat":
                    body["hoe_level"] = cap
                r = client.post(API, json=body)
                r.raise_for_status()
                data = r.json()
                titles = [s["title"] for s in data["retrieved"]]
                row = {
                    "question": question,
                    "gold": gold,
                    "target_level": target,
                    "cap": cap,
                    "hit_at_3": gold in titles,
                    "returned": " | ".join(titles),
                    "returned_levels": ",".join(str(s["hoe_level"]) for s in data["retrieved"]),
                    "latency_ms": round(data["latency_ms"]),
                    "answer_chars": len(data["answer"]),
                }
                rows.append(row)
                print(f"{cap!s:>5}  hit={row['hit_at_3']!s:<5}  {question[:55]}")

    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print("\nRecall@3 by depth cap:")
    for cap in CAPS:
        sub = [r for r in rows if r["cap"] == cap]
        print(f"  cap={cap!s:<5} {sum(r['hit_at_3'] for r in sub)}/{len(sub)}")

    matched = [r for r in rows if r["cap"] == r["target_level"]]
    print(f"Matched-level recall (cap = target level): "
          f"{sum(r['hit_at_3'] for r in matched)}/{len(matched)}")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    run()