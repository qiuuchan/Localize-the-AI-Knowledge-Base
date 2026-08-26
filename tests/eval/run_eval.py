"""KB-AI · RAG 检索回归评测(黄金问答集)

用法:
    backend/.venv/Scripts/python tests/eval/run_eval.py [--dataset PATH] [--base-url URL] [--top-k 5]
    # 或作为库:
    from tests.eval.run_eval import run_evaluation
    result = run_evaluation(base_url=..., dataset_path=..., top_k=5)

前提:
    1. FastAPI 后端已启动(scripts/start-backend.ps1 或 start.bat)
    2. Qdrant 容器已启动且知识库已入库

成本说明:
    每个问题仅调用 1 次 embedding(检索需要),不调用 LLM,费用可忽略。

数据集格式(jsonl,每行一条):
    {"question": "招牌菜有哪些?", "expect_source": "menu.md", "expect_keywords": ["招牌"]}
    - question:       用户问题
    - expect_source:  期望召回的文档名(在召回结果的 JSON 中做子串匹配)
    - expect_keywords:期望出现在召回文本中的关键词(可选,全部命中才算过)

退出码: 0 全部通过;1 有失败或用例数为 0;2 后端不可达。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List


def load_dataset(path: str) -> list[dict]:
    cases = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"[ERROR] 第 {lineno} 行 JSON 解析失败: {exc}")
                sys.exit(1)
            if "question" not in case or "expect_source" not in case:
                print(f"[ERROR] 第 {lineno} 行缺少 question / expect_source 字段")
                sys.exit(1)
            cases.append(case)
    return cases


def _run_case_http_and_validate(base_url: str, case: dict, top_k: int, no_rerank: bool):
    params = {"question": case["question"], "top_k": top_k}
    if no_rerank:
        params["rerank_top_n"] = 0
    url = f"{base_url}/api/debug/retrieval?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=240) as response:
            data = json.loads(response.read().decode("utf-8"))
    except TimeoutError:
        return False, "请求超时(240s)", {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:200]
        return False, f"HTTP {exc.code}: {detail}", {}

    hits = data.get("reranked_hits") or data.get("rrf_hits") or []
    hits_json = json.dumps(hits, ensure_ascii=False)
    matching = [
        hit for hit in hits
        if case["expect_source"] in json.dumps(hit, ensure_ascii=False)
    ]
    failures = []
    if not hits:
        failures.append("召回为空")
    if not matching:
        failures.append(f"未召回期望文档 '{case['expect_source']}'")
    for keyword in case.get("expect_keywords", []):
        if keyword not in hits_json:
            failures.append(f"召回文本缺少关键词 '{keyword}'")
    if "expect_year" in case and not any(
        int(case["expect_year"]) in [int(value) for value in hit.get("year_mentions") or []]
        for hit in matching
    ):
        failures.append(f"期望年份未命中: {case['expect_year']}")
    if "expect_chunk_type" in case and not any(
        hit.get("chunk_type") == case["expect_chunk_type"] for hit in matching
    ):
        failures.append(f"chunk_type 未命中: {case['expect_chunk_type']}")
    return not failures, "; ".join(failures), data


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return round(ordered[index], 2)


def run_case_detailed(
    base_url: str,
    case: dict,
    top_k: int,
    no_rerank: bool = False,
) -> tuple[bool, str, dict[str, Any]]:
    started = time.perf_counter()
    ok, detail, data = _run_case_http_and_validate(base_url, case, top_k, no_rerank)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    limit = case.get("max_retrieval_ms")
    if limit is not None and elapsed_ms > float(limit):
        ok = False
        detail = "; ".join(part for part in (detail, f"检索耗时 {elapsed_ms}ms 超过 {limit}ms") if part)
    return ok, detail, {
        "elapsed_ms": elapsed_ms,
        "category": case.get("category", "uncategorized"),
        "data": data,
    }


def run_case(
    base_url: str,
    case: dict,
    top_k: int,
    no_rerank: bool = False,
) -> tuple[bool, str]:
    ok, detail, _meta = run_case_detailed(base_url, case, top_k, no_rerank)
    return ok, detail


# ---------------------------------------------------------------------------
# v0.8.11(P2.1):结构化执行入口 — 供 /api/eval/run 调用
# ---------------------------------------------------------------------------


def run_evaluation(
    base_url: str = "http://127.0.0.1:8000",
    dataset_path: str = "tests/eval/golden-qa.jsonl",
    top_k: int = 5,
    no_rerank: bool = False,
) -> Dict[str, Any]:
    """Run all golden-QA cases and return a structured result.

    保留既有执行结果字段,并返回按 category 汇总的通过率与 long 类延迟统计。
    """
    started = datetime.now(timezone.utc)
    try:
        cases = load_dataset(dataset_path)
    except FileNotFoundError:
        return {
            "dataset": dataset_path,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "pass_rate": 0.0,
            "duration_seconds": 0.0,
            "results": [],
            "timestamp": started.isoformat(),
            "base_url": base_url,
            "top_k": top_k,
            "category_stats": {},
            "latency_ms": {},
            "error": f"数据集不存在: {dataset_path}",
        }
    if not cases:
        return {
            "dataset": dataset_path,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "pass_rate": 0.0,
            "duration_seconds": 0.0,
            "results": [],
            "timestamp": started.isoformat(),
            "base_url": base_url,
            "top_k": top_k,
            "category_stats": {},
            "latency_ms": {},
            "error": f"数据集为空: {dataset_path}",
        }

    results: List[Dict[str, Any]] = []
    category_stats: Dict[str, Dict[str, Any]] = {}
    long_latencies: List[float] = []
    passed = 0
    for case in cases:
        ok, detail, meta = run_case_detailed(base_url, case, top_k, no_rerank)
        category = meta["category"]
        elapsed_ms = meta["elapsed_ms"]
        results.append(
            {
                "question": case["question"],
                "expect_source": case["expect_source"],
                "expect_keywords": case.get("expect_keywords", []),
                "category": category,
                "elapsed_ms": elapsed_ms,
                "ok": ok,
                "detail": detail,
            }
        )
        stats = category_stats.setdefault(
            category,
            {"total": 0, "passed": 0, "failed": 0, "pass_rate": 0.0},
        )
        stats["total"] += 1
        stats["passed"] += int(ok)
        stats["failed"] += int(not ok)
        if category == "long":
            long_latencies.append(elapsed_ms)
        passed += int(ok)

    for stats in category_stats.values():
        stats["pass_rate"] = round(stats["passed"] / stats["total"], 4)

    if long_latencies:
        ordered = sorted(long_latencies)
        midpoint = len(ordered) // 2
        if len(ordered) % 2:
            p50 = ordered[midpoint]
        else:
            p50 = (ordered[midpoint - 1] + ordered[midpoint]) / 2
        latency_ms = {
            "count": len(ordered),
            "p50": round(p50, 2),
            "p95": _p95(ordered),
            "max": round(ordered[-1], 2),
        }
    else:
        latency_ms = {"count": 0, "p50": None, "p95": None, "max": None}

    finished = datetime.now(timezone.utc)
    return {
        "dataset": dataset_path,
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "pass_rate": round(passed / len(cases), 4) if cases else 0.0,
        "duration_seconds": round((finished - started).total_seconds(), 2),
        "results": results,
        "timestamp": finished.isoformat(),
        "base_url": base_url,
        "top_k": top_k,
        "category_stats": category_stats,
        "latency_ms": latency_ms,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="KB-AI RAG 检索回归评测")
    ap.add_argument("--dataset", default="tests/eval/golden-qa.jsonl")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--no-rerank", action="store_true",
                    help="跳过 cross-encoder 重排(rerank_top_n=0);模型未下载时可用来先验召回链路")
    args = ap.parse_args()

    try:
        cases = load_dataset(args.dataset)
    except FileNotFoundError:
        print(f"[ERROR] 数据集不存在: {args.dataset}")
        print("        请复制 golden-qa.example.jsonl 并按实际知识库内容填写")
        return 1
    if not cases:
        print(f"[ERROR] 数据集为空: {args.dataset}")
        return 1

    print(f"数据集: {args.dataset}({len(cases)} 条)")
    print(f"端点:   {args.base_url}/api/debug/retrieval (top_k={args.top_k})")
    print("-" * 60)

    try:
        passed = 0
        for i, case in enumerate(cases, 1):
            ok, detail = run_case(args.base_url, case, args.top_k, args.no_rerank)
            mark = "PASS" if ok else "FAIL"
            print(f"[{mark}] #{i} {case['question'][:40]}")
            if not ok:
                print(f"       原因: {detail}")
            passed += ok
    except urllib.error.URLError as exc:
        print(f"[ERROR] 后端不可达({exc});请先启动后端与 Qdrant")
        return 2

    print("-" * 60)
    print(f"通过: {passed}/{len(cases)}")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
