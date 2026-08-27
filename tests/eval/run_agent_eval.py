"""KB-AI · Agent 评测(工具选择 + 任务完成)

用法:
    backend/.venv/Scripts/python tests/eval/run_agent_eval.py [--dataset PATH] [--base-url URL] [--max-steps 8]
    # 或作为库:
    from tests.eval.run_agent_eval import run_evaluation
    result = run_evaluation(base_url=..., dataset_path=..., max_steps=8)

前提:
    1. FastAPI 后端已启动(scripts/start-backend.ps1 或 start.bat)
    2. Qdrant 容器已启动且知识库已入库
    3. .env 已配置 LLM key(agent loop 每步都调 LLM,多步放大 token 消耗)

成本说明:
    每条用例调用 1..N 次 LLM(max_steps 内);qwen3.6-plus 思考型模型
    reasoning_tokens 计入计费。23 条全量 ≈ 40-90 次 LLM 调用,量级几毛~几元。

数据集格式(jsonl,每行一条):
    {"question": "...", "expect_tools": ["kb_search"], "expect_keywords": ["%"], "category": "kb_only"}
    - question:       用户问题
    - expect_tools:   期望用到的工具(子集判定:实际 ⊇ 期望)
    - expect_keywords:期望出现在最终 answer 中的关键词(可空 = 只验 answer 非空)
    - category:       分类(用于汇总)

指标(设计稿 §8):
    - 工具选择准确率: 每条 tools_used ⊇ expect_tools 的比率
    - 任务完成率:      answer 非空且 keywords 全命中 的比率
    - 效率:            平均步数 / p95 端到端延迟 / 每任务 token 成本(total_in+total_out)

退出码: 0 全部通过;1 有失败或用例数为 0;2 后端不可达。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
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
            if "question" not in case or "expect_tools" not in case:
                print(f"[ERROR] 第 {lineno} 行缺少 question / expect_tools 字段")
                sys.exit(1)
            if not isinstance(case["expect_tools"], list) or not case["expect_tools"]:
                print(f"[ERROR] 第 {lineno} 行 expect_tools 必须是非空数组")
                sys.exit(1)
            cases.append(case)
    return cases


def _p95(values: List[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return round(ordered[index], 2)


def _post_agent_chat(
    base_url: str,
    question: str,
    max_steps: int,
    timeout: int = 300,
) -> Dict[str, Any]:
    """POST /api/agent/chat 并解析 SSE 事件流,聚合单次运行的观测。

    返回:
      {tools_used[], answer, citations[], steps, total_in, total_out,
       elapsed_ms, error, stream_ok}
    """
    body = json.dumps({"question": question, "max_steps": max_steps, "top_k": 5}).encode()
    req = urllib.request.Request(
        f"{base_url}/api/agent/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    tools_used: List[str] = []
    answer = ""
    citations: List[Dict[str, Any]] = []
    steps = 0
    total_in = 0
    total_out = 0
    error: str | None = None
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:  # 按行迭代 SSE 帧
            line = raw.decode("utf-8").rstrip()
            if not line.startswith("data:"):
                continue
            try:
                evt = json.loads(line[len("data:"):].strip())
            except json.JSONDecodeError:
                continue
            evt_type = evt.get("type")
            if evt_type == "tool_call" and evt.get("name"):
                tools_used.append(evt["name"])
            elif evt_type == "tool_result" and evt.get("step") is not None:
                steps = max(steps, int(evt["step"]))
            elif evt_type == "step_start" and evt.get("step") is not None:
                steps = max(steps, int(evt["step"]))
            elif evt_type == "answer":
                answer = evt.get("content") or ""
                citations = evt.get("citations") or []
                agent = evt.get("agent") or {}
                steps = max(steps, int(agent.get("steps") or 0))
                total_in = int(agent.get("total_in") or 0)
                total_out = int(agent.get("total_out") or 0)
            elif evt_type == "error":
                error = evt.get("message") or "未知错误"
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    # 去重保序:工具选择判定用集合,但展示保留首次出现顺序
    seen: set[str] = set()
    unique_tools = [t for t in tools_used if not (t in seen or seen.add(t))]
    return {
        "tools_used": unique_tools,
        "answer": answer,
        "citations": citations,
        "steps": steps,
        "total_in": total_in,
        "total_out": total_out,
        "elapsed_ms": elapsed_ms,
        "error": error,
        "stream_ok": error is None,
    }


def run_case_detailed(
    base_url: str,
    case: dict,
    max_steps: int,
) -> tuple[bool, str, Dict[str, Any]]:
    expect_tools = set(case["expect_tools"])
    expect_keywords = case.get("expect_keywords") or []
    failures: List[str] = []
    try:
        obs = _post_agent_chat(base_url, case["question"], max_steps)
    except TimeoutError:
        return False, "请求超时(300s)", {"category": case.get("category", "uncategorized"), "elapsed_ms": None}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:200]
        return False, f"HTTP {exc.code}: {detail}", {"category": case.get("category", "uncategorized"), "elapsed_ms": None}

    actual = set(obs["tools_used"])
    # 工具选择准确率:实际 ⊇ 期望(允许模型多调,不允许少调)
    missing_tools = expect_tools - actual
    if missing_tools:
        failures.append(f"未调用期望工具: {sorted(missing_tools)}(实际: {sorted(actual) or '无'})")
    if obs["error"]:
        failures.append(f"stream error: {obs['error'][:120]}")
    # 任务完成:answer 非空 + keywords 全命中
    answer = (obs["answer"] or "").strip()
    if not answer:
        failures.append("answer 为空")
    else:
        for kw in expect_keywords:
            if kw not in answer:
                failures.append(f"answer 缺少关键词 '{kw}'")

    meta: Dict[str, Any] = {
        "category": case.get("category", "uncategorized"),
        "elapsed_ms": obs["elapsed_ms"],
        "tools_used": obs["tools_used"],
        "steps": obs["steps"],
        "total_in": obs["total_in"],
        "total_out": obs["total_out"],
        "answer_preview": answer[:120],
    }
    return not failures, "; ".join(failures) or "ok", meta


def run_case(base_url: str, case: dict, max_steps: int) -> tuple[bool, str]:
    ok, detail, _ = run_case_detailed(base_url, case, max_steps)
    return ok, detail


def run_evaluation(
    base_url: str = "http://127.0.0.1:8000",
    dataset_path: str = "tests/eval/golden-agent.jsonl",
    max_steps: int = 8,
) -> Dict[str, Any]:
    """结构化执行入口(对齐 run_eval.py::run_evaluation),供 CLI 与未来 /api/eval 复用。"""
    started = datetime.now(timezone.utc)
    try:
        cases = load_dataset(dataset_path)
    except FileNotFoundError:
        return {"dataset": dataset_path, "total": 0, "passed": 0, "failed": 0,
                "pass_rate": 0.0, "duration_seconds": 0.0, "results": [],
                "timestamp": started.isoformat(), "base_url": base_url,
                "max_steps": max_steps, "category_stats": {}, "latency_ms": {},
                "error": f"数据集不存在: {dataset_path}"}
    if not cases:
        return {"dataset": dataset_path, "total": 0, "passed": 0, "failed": 0,
                "pass_rate": 0.0, "duration_seconds": 0.0, "results": [],
                "timestamp": started.isoformat(), "base_url": base_url,
                "max_steps": max_steps, "category_stats": {}, "latency_ms": {},
                "error": f"数据集为空: {dataset_path}"}

    results: List[Dict[str, Any]] = []
    category_stats: Dict[str, Dict[str, Any]] = {}
    all_elapsed: List[float] = []
    total_in = 0
    total_out = 0
    steps_sum = 0
    tools_ok = 0
    task_ok = 0
    passed = 0
    for i, case in enumerate(cases, 1):
        ok, detail, meta = run_case_detailed(base_url, case, max_steps)
        category = meta["category"]
        results.append({
            "question": case["question"],
            "expect_tools": case["expect_tools"],
            "expect_keywords": case.get("expect_keywords", []),
            "category": category,
            "ok": ok,
            "detail": detail,
            "elapsed_ms": meta["elapsed_ms"],
            "tools_used": meta["tools_used"],
            "steps": meta["steps"],
            "total_in": meta["total_in"],
            "total_out": meta["total_out"],
            "answer_preview": meta["answer_preview"],
        })
        stats = category_stats.setdefault(category, {"total": 0, "passed": 0, "failed": 0, "pass_rate": 0.0})
        stats["total"] += 1
        stats["passed"] += int(ok)
        stats["failed"] += int(not ok)
        passed += int(ok)
        if meta["elapsed_ms"] is not None:
            all_elapsed.append(meta["elapsed_ms"])
        if meta["steps"]:
            steps_sum += meta["steps"]
        total_in += meta["total_in"]
        total_out += meta["total_out"]
        # 工具选择准确率(仅对能拿到 tools_used 的 case)
        if set(case["expect_tools"]) <= set(meta["tools_used"]):
            tools_ok += 1
        # 任务完成率(answer 非空 + keywords 命中;对 error case 记为失败)
        answer_ok = bool((meta["answer_preview"] or "").strip()) and all(
            kw in meta["answer_preview"] for kw in (case.get("expect_keywords") or [])
        )
        if answer_ok and meta["elapsed_ms"] is not None:
            task_ok += 1

    for stats in category_stats.values():
        stats["pass_rate"] = round(stats["passed"] / stats["total"], 4)

    n = len(cases)
    finished = datetime.now(timezone.utc)
    return {
        "dataset": dataset_path,
        "total": n,
        "passed": passed,
        "failed": n - passed,
        "pass_rate": round(passed / n, 4) if n else 0.0,
        "duration_seconds": round((finished - started).total_seconds(), 2),
        "results": results,
        "timestamp": finished.isoformat(),
        "base_url": base_url,
        "max_steps": max_steps,
        "category_stats": category_stats,
        "tools_accuracy": round(tools_ok / n, 4) if n else 0.0,
        "task_completion_rate": round(task_ok / n, 4) if n else 0.0,
        "avg_steps": round(steps_sum / n, 2) if n else 0.0,
        "total_tokens": total_in + total_out,
        "avg_tokens_per_task": round((total_in + total_out) / n, 1) if n else 0.0,
        "latency_ms": {
            "count": len(all_elapsed),
            "p50": round(sorted(all_elapsed)[len(all_elapsed) // 2], 2) if all_elapsed else None,
            "p95": _p95(all_elapsed),
            "max": round(max(all_elapsed), 2) if all_elapsed else None,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="KB-AI Agent 评测(工具选择 + 任务完成)")
    ap.add_argument("--dataset", default="tests/eval/golden-agent.jsonl")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument("--json", action="store_true", help="只输出 JSON 结果(供 CI/脚本消费)")
    args = ap.parse_args()

    try:
        cases = load_dataset(args.dataset)
    except FileNotFoundError:
        print(f"[ERROR] 数据集不存在: {args.dataset}")
        return 1
    if not cases:
        print(f"[ERROR] 数据集为空: {args.dataset}")
        return 1

    if not args.json:
        print(f"数据集: {args.dataset}({len(cases)} 条)")
        print(f"端点:   {args.base_url}/api/agent/chat (max_steps={args.max_steps})")
        print("-" * 64)

    try:
        result = run_evaluation(args.base_url, args.dataset, args.max_steps)
    except urllib.error.URLError as exc:
        print(f"[ERROR] 后端不可达({exc});请先启动后端与 Qdrant")
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["failed"] == 0 else 1

    for i, r in enumerate(result["results"], 1):
        mark = "PASS" if r["ok"] else "FAIL"
        print(f"[{mark}] #{i} [{r['category']}] {r['question'][:36]}")
        print(f"       工具={r['tools_used'] or '无'} 步数={r['steps']} "
              f"耗时={r['elapsed_ms']}ms tokens={r['total_in'] + r['total_out']}")
        if not r["ok"]:
            print(f"       原因: {r['detail']}")
    print("-" * 64)
    print(f"通过: {result['passed']}/{result['total']} (pass_rate={result['pass_rate']})")
    print(f"工具选择准确率: {result['tools_accuracy']} | "
          f"任务完成率: {result['task_completion_rate']} | "
          f"平均步数: {result['avg_steps']}")
    print(f"p95 延迟: {result['latency_ms']['p95']}ms | "
          f"总 tokens: {result['total_tokens']} | "
          f"每任务 tokens: {result['avg_tokens_per_task']}")
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
