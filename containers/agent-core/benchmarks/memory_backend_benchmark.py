#!/usr/bin/env python3
"""Benchmark AgentWASP memory backends with a fixed local reader model.

This harness compares the context that a local-model AgentWASP reader sees when
memory comes from:

- internal: AgentWASP's lightweight local-model recent episodic context path
- supermemory: scoped Supermemory profile/search context
- tandem: Supermemory context plus the same recent internal episodic context

The benchmark is intentionally synthetic and non-secret. It measures retrieval
support, answer correctness, abstention, distractor resistance, prompt size, and
latency while keeping the reader model, prompts, questions, and memory corpus
fixed across backends.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "gemma-4-12b-it-q4km-vulkan-safe"
DEFAULT_BASE_URL = "http://127.0.0.1:8088/v1"
DEFAULT_SUPERMEMORY_BASE_URL = "http://127.0.0.1:8787"
DEFAULT_FIXTURE = Path(__file__).parent / "fixtures" / "memory_benchmark_cases.json"
SYSTEM_PROMPT = """You are evaluating an agent memory backend. Use ONLY the supplied memory context and recent chat context. If the answer is not explicitly supported, answer UNKNOWN. Return compact JSON only: {\"answer\":\"...\",\"evidence\":\"...\",\"confidence\":0.0}."""


class HttpError(RuntimeError):
    pass


def _json_request(method: str, url: str, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: float = 30.0) -> tuple[int, dict[str, Any], float]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            elapsed = time.perf_counter() - started
            body = json.loads(raw) if raw.strip() else {}
            return response.status, body, elapsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        elapsed = time.perf_counter() - started
        try:
            body = json.loads(raw) if raw.strip() else {"error": raw}
        except json.JSONDecodeError:
            body = {"error": raw}
        raise HttpError(f"{method} {url} failed with HTTP {exc.code} after {elapsed:.2f}s: {str(body)[:240]}") from exc
    except (TimeoutError, urllib.error.URLError, OSError) as exc:
        elapsed = time.perf_counter() - started
        raise HttpError(f"{method} {url} failed after {elapsed:.2f}s: {type(exc).__name__}: {str(exc)[:180]}") from exc


def _normalise(text: str) -> str:
    return " ".join((text or "").lower().replace("\u2019", "'").split())


def _phrase_in_text(text: str, phrase: str) -> bool:
    norm_text = _normalise(text)
    norm_phrase = _normalise(phrase)
    if not norm_phrase:
        return True
    # Avoid false hits such as forbidden `800` matching expected `1800`.
    pattern = r"(?<![a-z0-9])" + re.escape(norm_phrase) + r"(?![a-z0-9])"
    return re.search(pattern, norm_text) is not None


def _contains_all(text: str, required: list[str]) -> bool:
    return all(_phrase_in_text(text, item) for item in required)


def _contains_any(text: str, candidates: list[str]) -> bool:
    return any(_phrase_in_text(text, item) for item in candidates)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[idx]


def _safe_model_response_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = (choices[0] or {}).get("message") or {}
    return str(message.get("content") or "")


def _answer_payload(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    # Gemma may wrap JSON in fences or text; salvage the first object if present.
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            if isinstance(parsed, dict):
                parsed["_salvaged"] = True
                return parsed
        except json.JSONDecodeError:
            pass
    return {"answer": raw, "evidence": "", "confidence": None, "_parse_error": True}


def load_cases(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if "cases" not in data:
        raise ValueError(f"Fixture {path} has no cases")
    return data


def build_internal_context(case: dict[str, Any], recent_limit: int) -> tuple[str, float, dict[str, Any]]:
    started = time.perf_counter()
    # AgentWASP local-model mode appends only a bounded number of recent,
    # chat-scoped episodic turns. Facts older than the configured recent-turn
    # window are intentionally invisible to this baseline.
    facts = [
        f for f in case["facts"]
        if f.get("chat") == "primary" and int(f.get("turns_ago", 0)) <= recent_limit
    ]
    recent = sorted(facts, key=lambda f: int(f.get("turns_ago", 0)), reverse=True)
    if not recent:
        block = ""
    else:
        lines = ["[AGENTWASP RECENT EPISODIC CONTEXT]"]
        for fact in recent:
            lines.append(f"- {fact['content']}")
        block = "\n".join(lines)
    return block, time.perf_counter() - started, {"recent_count": len(recent)}


def supermemory_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def supermemory_container(run_tag: str, case_id: str, chat: str = "primary") -> str:
    return f"{run_tag}:case:{case_id}:chat:{chat}"


def seed_supermemory_case(base_url: str, api_key: str, run_tag: str, case: dict[str, Any], timeout: float) -> tuple[int, float, int, list[str]]:
    started = time.perf_counter()
    count = 0
    failures = 0
    error_samples: list[str] = []
    for fact in case["facts"]:
        # Match AgentWASP Supermemory chat scope: one container per chat.
        container = supermemory_container(run_tag, case["id"], fact.get("chat", "primary"))
        payload = {
            "containerTag": container,
            "memories": [
                {
                    "content": fact["content"],
                    "isStatic": False,
                    "metadata": {
                        "benchmark": "agentwasp-memory-v1",
                        "case_id": case["id"],
                        "category": case.get("category", ""),
                        "chat": fact.get("chat", "primary"),
                        "turns_ago": fact.get("turns_ago"),
                    },
                }
            ],
        }
        try:
            _json_request("POST", f"{base_url.rstrip('/')}/v4/memories", payload, supermemory_headers(api_key), timeout=timeout)
            count += 1
        except Exception as exc:
            failures += 1
            if len(error_samples) < 3:
                error_samples.append(str(exc).splitlines()[0][:220])
    return count, time.perf_counter() - started, failures, error_samples


def get_supermemory_context(base_url: str, api_key: str, run_tag: str, case: dict[str, Any], timeout: float, limit: int, budget_chars: int) -> tuple[str, float, dict[str, Any]]:
    payload = {
        "containerTag": supermemory_container(run_tag, case["id"], "primary"),
        "q": case["question"],
        "limit": limit,
        "threshold": 0.0,
        "rerank": False,
        "rewriteQuery": False,
    }
    try:
        status, data, elapsed = _json_request("POST", f"{base_url.rstrip('/')}/v4/profile", payload, supermemory_headers(api_key), timeout=timeout)
    except Exception as exc:
        elapsed = timeout
        return "[SUPERMEMORY CONTEXT UNAVAILABLE]", elapsed, {"error": str(exc).splitlines()[0][:180], "dynamic_count": 0, "search_count": 0, "total": 0}
    profile = data.get("profile") or {}
    static = profile.get("static") or []
    dynamic = profile.get("dynamic") or []
    results_obj = data.get("searchResults") or {}
    results = results_obj.get("results") or []
    lines: list[str] = []
    if static:
        lines.append("Static profile:")
        lines.extend(f"- {str(item)[:240]}" for item in static[:4])
    if dynamic:
        lines.append("Recent context:")
        lines.extend(f"- {str(item)[:260]}" for item in dynamic[:limit])
    if results:
        lines.append("Relevant memories:")
        for result in results[:limit]:
            if isinstance(result, dict):
                memory = result.get("memory") or result.get("content") or result.get("summary") or result.get("title")
                sim = result.get("similarity") or result.get("score")
                prefix = f"({float(sim):.2f}) " if isinstance(sim, (int, float)) else ""
                if memory:
                    lines.append(f"- {prefix}{str(memory)[:260]}")
            elif result:
                lines.append(f"- {str(result)[:260]}")
    block = "[SUPERMEMORY CONTEXT]\n" + "\n".join(lines) if lines else ""
    if len(block) > budget_chars:
        block = block[: budget_chars - 1].rstrip() + "…"
    meta = {"http_status": status, "dynamic_count": len(dynamic), "search_count": len(results), "total": results_obj.get("total")}
    return block, elapsed, meta


def build_messages(context: str, question: str) -> list[dict[str, str]]:
    user = f"MEMORY CONTEXT:\n{context or '[no memory context retrieved]'}\n\nQUESTION: {question}\n\nRemember: answer only from supplied memory context. If unsupported, answer UNKNOWN."
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def call_reader(base_url: str, model: str, messages: list[dict[str, str]], timeout: float, max_tokens: int) -> tuple[str, float, dict[str, Any]]:
    payload = {"model": model, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
    status, data, elapsed = _json_request("POST", f"{base_url.rstrip('/')}/chat/completions", payload, timeout=timeout)
    text = _safe_model_response_text(data)
    return text, elapsed, {"http_status": status, "usage": data.get("usage") or {}, "timings": data.get("timings") or {}}


def score_case(case: dict[str, Any], context: str, raw_answer: str, reader_meta: dict[str, Any], retrieval_latency: float, generation_latency: float, extra: dict[str, Any]) -> dict[str, Any]:
    expected = case.get("expected") or []
    forbidden = case.get("forbidden") or []
    abstain = bool(case.get("abstain"))
    parsed = _answer_payload(raw_answer)
    answer_text = str(parsed.get("answer") or raw_answer)
    full_answer_text = json.dumps(parsed, ensure_ascii=False)
    context_has_expected = _contains_all(context, [e for e in expected if _normalise(e) != "unknown"])
    context_has_forbidden = _contains_any(context, forbidden)
    answer_forbidden_hit = _contains_any(answer_text, forbidden)
    full_forbidden_hit = _contains_any(full_answer_text, forbidden)
    if abstain:
        answer_correct = "unknown" in _normalise(answer_text) and not answer_forbidden_hit
    else:
        answer_correct = _contains_all(full_answer_text, expected) and not full_forbidden_hit
    usage = reader_meta.get("usage") or {}
    return {
        "case_id": case["id"],
        "category": case.get("category", ""),
        "question": case["question"],
        "expected": "; ".join(expected),
        "abstain_expected": abstain,
        "answer": answer_text,
        "answer_correct": bool(answer_correct),
        "context_has_expected": bool(context_has_expected if not abstain else True),
        "context_has_forbidden": bool(context_has_forbidden),
        "forbidden_hit": bool(answer_forbidden_hit),
        "unsupported_answer": bool((not context_has_expected) and (not abstain) and _contains_all(full_answer_text, expected)),
        "retrieval_latency_ms": round(retrieval_latency * 1000, 2),
        "generation_latency_ms": round(generation_latency * 1000, 2),
        "context_chars": len(context),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "parse_error": bool(parsed.get("_parse_error")),
        **extra,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_backend: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_backend.setdefault(row["backend"], []).append(row)
    summary: dict[str, Any] = {}
    for backend, group in by_backend.items():
        lat_r = [float(r["retrieval_latency_ms"]) for r in group]
        lat_g = [float(r["generation_latency_ms"]) for r in group]
        ctx = [int(r["context_chars"]) for r in group]
        toks = [int(r["total_tokens"] or 0) for r in group]
        categories: dict[str, Any] = {}
        for category in sorted({r["category"] for r in group}):
            subset = [r for r in group if r["category"] == category]
            categories[category] = {
                "cases": len(subset),
                "answer_accuracy": round(sum(bool(r["answer_correct"]) for r in subset) / len(subset), 4),
                "retrieval_support": round(sum(bool(r["context_has_expected"]) for r in subset) / len(subset), 4),
                "forbidden_answer_rate": round(sum(bool(r["forbidden_hit"]) for r in subset) / len(subset), 4),
            }
        summary[backend] = {
            "cases": len(group),
            "answer_accuracy": round(sum(bool(r["answer_correct"]) for r in group) / len(group), 4),
            "retrieval_support": round(sum(bool(r["context_has_expected"]) for r in group) / len(group), 4),
            "context_forbidden_rate": round(sum(bool(r["context_has_forbidden"]) for r in group) / len(group), 4),
            "forbidden_answer_rate": round(sum(bool(r["forbidden_hit"]) for r in group) / len(group), 4),
            "unsupported_answer_rate": round(sum(bool(r["unsupported_answer"]) for r in group) / len(group), 4),
            "avg_context_chars": round(statistics.mean(ctx), 1),
            "avg_total_tokens": round(statistics.mean(toks), 1),
            "retrieval_latency_ms_p50": round(statistics.median(lat_r), 2),
            "retrieval_latency_ms_p95": round(_p95(lat_r), 2),
            "generation_latency_ms_p50": round(statistics.median(lat_g), 2),
            "generation_latency_ms_p95": round(_p95(lat_g), 2),
            "categories": categories,
        }
    return summary


def write_outputs(out_dir: Path, rows: list[dict[str, Any]], summary: dict[str, Any], meta: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps({"meta": meta, "summary": summary, "rows": rows}, indent=2, ensure_ascii=False))
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with (out_dir / "results.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# AgentWASP Memory Benchmark Report",
        "",
        f"Generated: {meta['generated_at']}",
        f"Reader model: `{meta['reader_model']}` at `{meta['reader_base_url']}`",
        f"Cases: {meta['case_count']}",
        f"Run tag: `{meta['run_tag']}`",
        "",
        "## Summary by backend",
        "",
        "| Backend | Answer accuracy | Retrieval support | Forbidden answer rate | Avg context chars | p50 retrieval ms | p95 retrieval ms | p50 generation ms | Avg total tokens |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for backend, data in summary.items():
        lines.append(
            f"| {backend} | {data['answer_accuracy']:.1%} | {data['retrieval_support']:.1%} | {data['forbidden_answer_rate']:.1%} | {data['avg_context_chars']} | {data['retrieval_latency_ms_p50']} | {data['retrieval_latency_ms_p95']} | {data['generation_latency_ms_p50']} | {data['avg_total_tokens']} |"
        )
    lines.extend(["", "## Category breakdown", ""])
    for backend, data in summary.items():
        lines.append(f"### {backend}")
        lines.append("")
        lines.append("| Category | Cases | Answer accuracy | Retrieval support | Forbidden answer rate |")
        lines.append("|---|---:|---:|---:|---:|")
        for category, cdata in data["categories"].items():
            lines.append(f"| {category} | {cdata['cases']} | {cdata['answer_accuracy']:.1%} | {cdata['retrieval_support']:.1%} | {cdata['forbidden_answer_rate']:.1%} |")
        lines.append("")
    lines.extend([
        "## Methodology notes",
        "",
        "- Synthetic non-secret cases are fixed across backends.",
        "- The reader model, decoding settings, and scoring rules are fixed across backends.",
        "- `internal` models AgentWASP's local-model lightweight memory behavior: bounded recent chat-scoped episodic context.",
        "- `supermemory` uses scoped `/v4/memories` ingestion and `/v4/profile` retrieval against the configured Supermemory endpoint.",
        "- `tandem` concatenates the Supermemory block with the same internal recent context to measure recall upside versus prompt/latency cost.",
        "- This is not an official LongMemEval/LoCoMo leaderboard run; use it as an AgentWASP-specific backend comparison.",
        "",
    ])
    (out_dir / "report.md").write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--reader-base-url", default=os.getenv("AGENTWASP_BENCH_READER_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--reader-model", default=os.getenv("AGENTWASP_BENCH_READER_MODEL", DEFAULT_MODEL))
    parser.add_argument("--reader-timeout", type=float, default=90.0)
    parser.add_argument("--reader-max-tokens", type=int, default=96)
    parser.add_argument("--supermemory-base-url", default=os.getenv("SUPERMEMORY_BASE_URL", DEFAULT_SUPERMEMORY_BASE_URL))
    parser.add_argument("--supermemory-api-key", default=os.getenv("SUPERMEMORY_API_KEY", ""))
    parser.add_argument("--supermemory-api-key-file", type=Path, default=None, help="Read Supermemory API key from a local file without printing it.")
    parser.add_argument("--supermemory-timeout", type=float, default=20.0)
    parser.add_argument("--supermemory-limit", type=int, default=4)
    parser.add_argument("--context-budget-chars", type=int, default=1800)
    parser.add_argument("--internal-recent-turn-limit", type=int, default=None)
    parser.add_argument("--backends", nargs="+", default=["internal", "supermemory", "tandem"], choices=["internal", "supermemory", "tandem"])
    parser.add_argument("--out-dir", type=Path, default=Path("benchmark-results") / dt.datetime.now(dt.UTC).strftime("memory-%Y%m%d-%H%M%S"))
    parser.add_argument("--run-tag", default="agentwasp-bench-" + dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--skip-supermemory-seed", action="store_true", help="Assume Supermemory memories were already seeded for this run tag.")
    args = parser.parse_args()
    if args.supermemory_api_key_file and not args.supermemory_api_key:
        args.supermemory_api_key = args.supermemory_api_key_file.read_text().strip()

    fixture = load_cases(args.fixture)
    cases = fixture["cases"]
    recent_limit = args.internal_recent_turn_limit or int(fixture.get("internal_recent_turn_limit", 6))

    # Verify reader endpoint before mutating Supermemory.
    try:
        _json_request("GET", f"{args.reader_base_url.rstrip('/')}/models", timeout=10.0)
    except Exception as exc:
        print(f"Reader endpoint unavailable: {exc}", file=sys.stderr)
        return 2

    needs_sm = any(b in {"supermemory", "tandem"} for b in args.backends)
    if needs_sm and not args.supermemory_api_key:
        print("Supermemory API key required for supermemory/tandem backends. Set SUPERMEMORY_API_KEY or run only --backends internal.", file=sys.stderr)
        return 2

    seed_meta = {"seeded_memories": 0, "seed_latency_ms": 0.0, "seed_failures": 0, "seed_error_samples": []}
    if needs_sm and not args.skip_supermemory_seed:
        total_seeded = 0
        total_seed_failures = 0
        seed_error_samples: list[str] = []
        seed_started = time.perf_counter()
        for case in cases:
            count, _elapsed, failures, errors = seed_supermemory_case(args.supermemory_base_url, args.supermemory_api_key, args.run_tag, case, args.supermemory_timeout)
            total_seeded += count
            total_seed_failures += failures
            for error in errors:
                if len(seed_error_samples) < 5:
                    seed_error_samples.append(error)
        seed_meta = {
            "seeded_memories": total_seeded,
            "seed_latency_ms": round((time.perf_counter() - seed_started) * 1000, 2),
            "seed_failures": total_seed_failures,
            "seed_error_samples": seed_error_samples,
        }
        if total_seed_failures:
            print(f"WARNING: Supermemory seed had {total_seed_failures} failed writes; continuing so internal/degraded backends still produce a report.", file=sys.stderr)

    rows: list[dict[str, Any]] = []
    for case in cases:
        internal_context, internal_latency, internal_meta = build_internal_context(case, recent_limit)
        backend_contexts: dict[str, tuple[str, float, dict[str, Any]]] = {
            "internal": (internal_context, internal_latency, internal_meta),
        }
        if needs_sm:
            sm_context, sm_latency, sm_meta = get_supermemory_context(
                args.supermemory_base_url,
                args.supermemory_api_key,
                args.run_tag,
                case,
                args.supermemory_timeout,
                args.supermemory_limit,
                args.context_budget_chars,
            )
            backend_contexts["supermemory"] = (sm_context, sm_latency, sm_meta)
            tandem_context = "\n\n".join(part for part in [sm_context, internal_context] if part)
            backend_contexts["tandem"] = (tandem_context, sm_latency + internal_latency, {**sm_meta, **internal_meta})

        for backend in args.backends:
            context, retrieval_latency, extra = backend_contexts[backend]
            messages = build_messages(context, case["question"])
            raw_answer, gen_latency, reader_meta = call_reader(args.reader_base_url, args.reader_model, messages, args.reader_timeout, args.reader_max_tokens)
            row = score_case(case, context, raw_answer, reader_meta, retrieval_latency, gen_latency, extra)
            row["backend"] = backend
            rows.append(row)
            print(f"{backend:11s} {case['id']:28s} correct={row['answer_correct']} context={row['context_has_expected']} gen_ms={row['generation_latency_ms']} answer={str(row['answer'])[:80]}")

    summary = summarize(rows)
    meta = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "fixture": str(args.fixture),
        "case_count": len(cases),
        "reader_base_url": args.reader_base_url,
        "reader_model": args.reader_model,
        "supermemory_base_url": args.supermemory_base_url if needs_sm else None,
        "run_tag": args.run_tag,
        "backends": args.backends,
        "internal_recent_turn_limit": recent_limit,
        **seed_meta,
    }
    write_outputs(args.out_dir, rows, summary, meta)
    print(json.dumps({"out_dir": str(args.out_dir), "summary": summary, "meta": meta}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
