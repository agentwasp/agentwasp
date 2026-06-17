# AgentWASP Memory Benchmark Report

Generated: 2026-06-17T10:48:34.608267+00:00
Reader model: `gemma-4-12b-it-q4km-vulkan-safe` at `http://127.0.0.1:8088/v1`
Cases: 18
Run tag: `agentwasp-bench-20260617-104642`

## Summary by backend

| Backend | Answer accuracy | Retrieval support | Forbidden answer rate | Avg context chars | p50 retrieval ms | p95 retrieval ms | p50 generation ms | Avg total tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| internal | 44.4% | 44.4% | 0.0% | 91.6 | 0.01 | 0.02 | 1894.06 | 169.2 |
| supermemory | 88.9% | 94.4% | 5.6% | 138.7 | 142.44 | 8000.0 | 1395.99 | 180 |
| tandem | 88.9% | 94.4% | 5.6% | 232 | 142.45 | 8000.01 | 1508.05 | 207.9 |

## Category breakdown

### internal

| Category | Cases | Answer accuracy | Retrieval support | Forbidden answer rate |
|---|---:|---:|---:|---:|
| abstention | 1 | 100.0% | 100.0% | 0.0% |
| distractor_robustness | 2 | 0.0% | 0.0% | 0.0% |
| exact_value_recall | 1 | 0.0% | 0.0% | 0.0% |
| long_horizon_recall | 3 | 0.0% | 0.0% | 0.0% |
| multi_hop | 2 | 0.0% | 0.0% | 0.0% |
| procedure_recall | 1 | 0.0% | 0.0% | 0.0% |
| recent_recall_control | 2 | 100.0% | 100.0% | 0.0% |
| scope_isolation | 2 | 50.0% | 50.0% | 0.0% |
| stale_memory | 1 | 100.0% | 100.0% | 0.0% |
| temporal_update | 3 | 100.0% | 100.0% | 0.0% |

### supermemory

| Category | Cases | Answer accuracy | Retrieval support | Forbidden answer rate |
|---|---:|---:|---:|---:|
| abstention | 1 | 100.0% | 100.0% | 0.0% |
| distractor_robustness | 2 | 50.0% | 50.0% | 0.0% |
| exact_value_recall | 1 | 0.0% | 100.0% | 100.0% |
| long_horizon_recall | 3 | 100.0% | 100.0% | 0.0% |
| multi_hop | 2 | 100.0% | 100.0% | 0.0% |
| procedure_recall | 1 | 100.0% | 100.0% | 0.0% |
| recent_recall_control | 2 | 100.0% | 100.0% | 0.0% |
| scope_isolation | 2 | 100.0% | 100.0% | 0.0% |
| stale_memory | 1 | 100.0% | 100.0% | 0.0% |
| temporal_update | 3 | 100.0% | 100.0% | 0.0% |

### tandem

| Category | Cases | Answer accuracy | Retrieval support | Forbidden answer rate |
|---|---:|---:|---:|---:|
| abstention | 1 | 100.0% | 100.0% | 0.0% |
| distractor_robustness | 2 | 50.0% | 50.0% | 0.0% |
| exact_value_recall | 1 | 0.0% | 100.0% | 100.0% |
| long_horizon_recall | 3 | 100.0% | 100.0% | 0.0% |
| multi_hop | 2 | 100.0% | 100.0% | 0.0% |
| procedure_recall | 1 | 100.0% | 100.0% | 0.0% |
| recent_recall_control | 2 | 100.0% | 100.0% | 0.0% |
| scope_isolation | 2 | 100.0% | 100.0% | 0.0% |
| stale_memory | 1 | 100.0% | 100.0% | 0.0% |
| temporal_update | 3 | 100.0% | 100.0% | 0.0% |

## Methodology notes

- Synthetic non-secret cases are fixed across backends.
- The reader model, decoding settings, and scoring rules are fixed across backends.
- `internal` models AgentWASP's local-model lightweight memory behavior: bounded recent chat-scoped episodic context.
- `supermemory` uses scoped `/v4/memories` ingestion and `/v4/profile` retrieval against the configured Supermemory endpoint.
- `tandem` concatenates the Supermemory block with the same internal recent context to measure recall upside versus prompt/latency cost.
- This is not an official LongMemEval/LoCoMo leaderboard run; use it as an AgentWASP-specific backend comparison.
