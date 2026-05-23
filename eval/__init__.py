"""
Evaluation harness (Phase 11).

Turns the hybrid-retrieval improvements into measurable numbers:

    eval/dataset.py   — categorized evaluation queries
    eval/metrics.py   — precision@k, nDCG@k, MRR, citation-support rate
    eval/run_eval.py  — runs the dataset, computes metrics, writes a report

Run it (FastAPI backend must be up on :8000):

    python -m eval.run_eval
"""
