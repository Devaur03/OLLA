# Retrieval Benchmark Report

> Generated 2026-05-23 19:52 UTC · 2 queries · Phase 11 evaluation harness

## Headline

- **Latency speedup (web → warm hybrid):** 1.0×
  (2089 ms → 2086 ms mean)
- **Memory-served rate (warm hybrid):** 50% of queries answered from local memory without a web crawl
- **Query classification accuracy:** 100%

## Path comparison

| Metric | web (baseline) | hybrid cold | hybrid warm |
|---|---|---|---|
| queries ok | 2 | 2 | 2 |
| latency mean (ms) | 2089.25 | 2081.2 | 2085.6 |
| latency p50 (ms) | 2089.25 | 2081.2 | 2085.6 |
| latency p95 (ms) | 2099.195 | 2085.16 | 2085.87 |
| answer rate | 0.500 | 1.000 | 1.000 |
| mean results | 5.0 | 6.5 | 6.5 |
| citation support | 0.000 | 0.000 | 0.000 |
| precision@k | 0.700 | 0.400 | 0.400 |
| nDCG@k | 0.690 | 0.809 | 0.809 |
| MRR | 0.417 | 0.667 | 0.667 |

## Hybrid routing

Retrieval mode chosen (warm run):

- `hybrid` — 2

## Per-query detail

| id | category | web ms | warm ms | mode | from memory | p@k | classified |
|---|---|---|---|---|---|---|---|
| def-01 | definition | 2078.2 | 2085.3 | hybrid | False | 0.6 | ✓ |
| def-02 | definition | 2100.3 | 2085.9 | hybrid | True | 0.2 | ✓ |

---

Notes: precision@k / nDCG@k / MRR use domain-level relevance labels from `eval/dataset.py` and are averaged only over labelled queries. Citation support is a vocabulary-overlap heuristic, not a factual-entailment check.
