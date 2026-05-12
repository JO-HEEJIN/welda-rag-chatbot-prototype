"""Compare retrieval quality of two embedding models on a Korean query set.

Models: BAAI/bge-m3 (multilingual baseline) vs nlpai-lab/KURE-v1 (Korean-tuned).

For each model the script builds a fresh Chroma index over ``welda_knowledge/``,
runs every query in ``eval_queries.json``, and reports per-query plus aggregate
metrics (Precision@K, Recall@K, MRR, Hit@1, Hit@3, average latency). Detailed
results are written to ``evaluation/eval_results.json``.

Note on Precision@K: we compute ``sum(1 for f in retrieved_files if f in
relevant_set) / len(retrieved_files)`` so the numerator and denominator share
the same chunk-level unit. Set-based deduplication on the numerator alone
(while leaving the denominator as a list length) would underestimate precision
when several retrieved chunks come from the same relevant file.
"""

import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
for noisy in ("huggingface_hub", "huggingface_hub.utils._http", "transformers"):
    logging.getLogger(noisy).setLevel(logging.ERROR)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from langchain_chroma import Chroma  # noqa: E402
from langchain_core.documents import Document  # noqa: E402
from langchain_huggingface import HuggingFaceEmbeddings  # noqa: E402

from src.load_documents import load_and_split_documents

MODELS = {
    "bge-m3": "BAAI/bge-m3",
    "kure-v1": "nlpai-lab/KURE-v1",
}

TOP_K = 3
KNOWLEDGE_DIR = PROJECT_ROOT / "welda_knowledge"
QUERIES_PATH = PROJECT_ROOT / "evaluation" / "eval_queries.json"
RESULTS_PATH = PROJECT_ROOT / "evaluation" / "eval_results.json"
EVAL_DB_DIR = PROJECT_ROOT / "eval_db"


def build_temp_index(model_name: str, model_id: str, documents: list[Document]) -> Chroma:
    """Build (or rebuild) a Chroma index for the given embedding model."""
    embeddings = HuggingFaceEmbeddings(model_name=model_id)
    persist_dir = EVAL_DB_DIR / model_name

    if persist_dir.exists():
        shutil.rmtree(persist_dir)

    return Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=str(persist_dir),
        collection_name=f"welda_{model_name}",
    )


def calculate_metrics(retrieved_files: list[str], relevant_files: list[str]) -> dict:
    """Compute Precision@K, Recall@K, MRR, Hit@1, Hit@3 for a single query.

    ``retrieved_files`` is the chunk-level list of source filenames in rank
    order (length = TOP_K). ``relevant_files`` is the ground-truth set.
    """
    relevant_set = set(relevant_files)
    retrieved_set = set(retrieved_files)

    if retrieved_files:
        precision = sum(1 for f in retrieved_files if f in relevant_set) / len(retrieved_files)
    else:
        precision = 0.0

    recall = (
        len(relevant_set & retrieved_set) / len(relevant_set) if relevant_set else 0.0
    )

    mrr = 0.0
    for rank, file in enumerate(retrieved_files, start=1):
        if file in relevant_set:
            mrr = 1 / rank
            break

    hit_at_1 = 1 if retrieved_files and retrieved_files[0] in relevant_set else 0
    hit_at_3 = 1 if any(f in relevant_set for f in retrieved_files[:3]) else 0

    return {
        "precision": precision,
        "recall": recall,
        "mrr": mrr,
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
    }


def evaluate_model(vectorstore: Chroma, queries: list[dict]) -> dict:
    results = []
    latencies = []

    for q in queries:
        start = time.perf_counter()
        docs = vectorstore.similarity_search(q["query"], k=TOP_K)
        latency = time.perf_counter() - start
        latencies.append(latency)

        retrieved_files = [d.metadata.get("source_file", "unknown") for d in docs]
        metrics = calculate_metrics(retrieved_files, q["relevant_files"])
        metrics["query"] = q["query"]
        metrics["retrieved"] = retrieved_files
        metrics["expected"] = q["relevant_files"]
        results.append(metrics)

    n = len(results)
    aggregate = {
        "precision": sum(r["precision"] for r in results) / n,
        "recall": sum(r["recall"] for r in results) / n,
        "mrr": sum(r["mrr"] for r in results) / n,
        "hit_at_1": sum(r["hit_at_1"] for r in results) / n,
        "hit_at_3": sum(r["hit_at_3"] for r in results) / n,
        "avg_latency_ms": (sum(latencies) / n) * 1000,
    }

    return {"per_query": results, "aggregate": aggregate}


def main() -> None:
    documents = load_and_split_documents(str(KNOWLEDGE_DIR))
    print(f"[eval] Loaded {len(documents)} chunks from {KNOWLEDGE_DIR}")

    with open(QUERIES_PATH, encoding="utf-8") as f:
        queries = json.load(f)
    print(f"[eval] Loaded {len(queries)} queries from {QUERIES_PATH}\n")

    all_results: dict[str, dict] = {}
    for model_name, model_id in MODELS.items():
        print(f"=== {model_name} ({model_id}) ===")
        print("[eval] Building index...")
        t0 = time.perf_counter()
        vectorstore = build_temp_index(model_name, model_id, documents)
        print(f"[eval] Index built in {time.perf_counter() - t0:.1f}s")

        print(f"[eval] Running {len(queries)} queries...")
        result = evaluate_model(vectorstore, queries)
        all_results[model_name] = result

        print(f"[eval] {model_name} aggregate metrics:")
        for key, value in result["aggregate"].items():
            print(f"  {key:<16}{value:.4f}")
        print()

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"[eval] Detailed results saved to {RESULTS_PATH}\n")

    print("=== Comparison ===")
    print(f"{'Metric':<18}{'BGE-M3':>14}{'KURE-v1':>14}{'Winner':>14}")
    print("-" * 60)
    for metric in ["precision", "recall", "mrr", "hit_at_1", "hit_at_3", "avg_latency_ms"]:
        bge = all_results["bge-m3"]["aggregate"][metric]
        kure = all_results["kure-v1"]["aggregate"][metric]
        if metric == "avg_latency_ms":
            winner = "BGE-M3" if bge < kure else ("KURE-v1" if kure < bge else "Tie")
        else:
            winner = "BGE-M3" if bge > kure else ("KURE-v1" if kure > bge else "Tie")
        print(f"{metric:<18}{bge:>14.4f}{kure:>14.4f}{winner:>14}")


if __name__ == "__main__":
    main()
