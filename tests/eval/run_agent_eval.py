"""KB-AI · Agent 评测(工具选择 + 任务完成)

用法:
    backend/.venv/Scripts/python tests/eval/run_agent_eval.py [--dataset PATH] [--base-url URL] [--max-steps 8] [--judge keyword|llm]
    # 或作为库:
    from tests.eval.run_agent_eval import run_evaluation
    result = run_evaluation(base_url=..., dataset_path=..., max_steps=8)

v2.2 T11 新增(LLM-as-judge + 结果落库):
    --judge llm   :任务完成判定改用 LLM 语义裁判(替代关键词字面子串);
                    默认 keyword = 确定性/零成本/CI 可用,行为与 v2.1.0 完全一致。
    --input PATH  :跳过 Agent 实跑,读取已保存的评测结果 JSON(须含完整
                    answer 字段,见结果结构),用指定口径重新判定任务完成率。
    --no-persist  :不写 eval_runs 表(默认落库,同口径同日重跑幂等覆盖)。

前提:
    1. FastAPI 后端已启动(scripts/start-backend.ps1 或 start.bat)
    2. Qdrant 容器已启动且知识库已入库
    3. .env 已配置 LLM key(agent loop 每步都调 LLM,多步放大 token 消耗)

成本说明:
    每条用例调用 1..N 次 LLM(max_steps 内);qwen3.6-plus 思考型模型
    reasoning_tokens 计入计费。23 条全量 ≈ 40-90 次 LLM 调用,量级几毛~几元。
    --judge llm 另加 23 次 judge 调用(每次 1 轮,≈¥0.3-0.6)。

数据集格式(jsonl,每行一条):
    {"question": "...", "expect_tools": ["kb_search"], "expect_keywords": ["%"], "category": "kb_only"}
    - question:       用户问题
    - expect_tools:   期望用到的工具(子集判定:实际 ⊇ 期望)
    - expect_keywords:期望出现在最终 answer 中的关键词(可空 = 只验 answer 非空;
                      judge 口径下作为"期望答案要素"传给裁判做语义判定)
    - category:       分类(用于汇总)

指标(设计稿 §8):
    - 工具选择准确率: 每条 tools_used ⊇ expect_tools 的比率
    - 任务完成率:      answer 非空且 keywords 全命中 的比率(keyword 口径)
                       或 LLM 裁判判定任务完成 的比率(llm 口径)
    - 效率:            平均步数 / p95 端到端延迟 / 每任务 token 成本(total_in+total_out)

退出码: 0 全部通过;1 有失败或用例数为 0;2 后端不可达。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

# 脚本直接运行时(sys.path[0] = tests/eval/),把仓库根注入 sys.path,
# 使懒加载的 backend.*(judge 调用 / eval_runs 落库)可被 import。
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)


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


# ---------------------------------------------------------------------------
# v2.2 T11:LLM-as-judge(语义任务完成判定)
# ---------------------------------------------------------------------------

JUDGE_MODEL = "qwen3.6-plus"
JUDGE_MAX_TOKENS = 300

JUDGE_SYSTEM_PROMPT = (
    "你是 KB-AI 评测系统的裁判。你的唯一任务是判断 Agent 的最终回答是否"
    "真正完成了用户的任务。\n"
    "只输出 JSON,格式:\n"
    '{"complete": true 或 false, "reason": "一句话中文理由"}\n'
    "判定规则:\n"
    "1. 回答必须完整回答用户问题,答非所问或只回答一半都算 incomplete。\n"
    "2. 「期望答案要素」以语义等价为准:数值格式差异(5888 与 5,888)、"
    "百分比表述差异(22.37% 与 22.37 与 百分之二十二点三七)都算命中。\n"
    "3. 用户要求给出计算结果时,回答只描述过程、没有给出结果,判 incomplete。\n"
    "4. 回答明确表示\"无法获取/检索不到/暂时没有数据\",而任务要求给出"
    "数据结论时,判 incomplete;但若问题本身可如实说明未知,则判 complete。\n"
    "5. 只判断回答本身,不判断工具调用是否正确(工具选择由另一项指标负责)。"
)


def build_judge_messages(
    question: str,
    expect_tools: List[str],
    expect_keywords: List[str],
    tools_used: List[str],
    answer: str,
) -> List[Dict[str, Any]]:
    """构造 judge 单轮消息(一次 LLM 调用,非流式)。"""
    user = (
        f"任务: {question}\n"
        f"Agent 调用的工具: {tools_used or '无'}(期望工具: {expect_tools})\n"
        f"期望答案要素(语义等价即可,可空=不强制): {expect_keywords or '无'}\n"
        f"Agent 最终回答:\n---\n{answer or '(空)'}\n---\n"
        "请判定任务是否完成,输出 JSON。"
    )
    return [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def parse_judge_response(text: str) -> tuple[bool, str, str]:
    """解析 judge 输出 → (complete, reason, parse_mode)。

    parse_mode ∈ {'json', 'fallback'}:json 为结构化解析成功;fallback 为
    解析失败后降级到关键词口径(确定性,不因裁判输出格式而误判)。
    """
    if not text:
        return False, "judge 输出为空", "fallback"
    stripped = text.strip()
    # 剥 markdown 代码围栏(```json ... ``` / ``` ... ```)
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        start = stripped.index("{")
        end = stripped.rindex("}")
        payload = json.loads(stripped[start : end + 1])
        complete = bool(payload.get("complete"))
        reason = str(payload.get("reason") or "").strip() or "无理由"
        return complete, reason, "json"
    except (ValueError, json.JSONDecodeError):
        return False, "judge 输出非合法 JSON,已降级为关键词口径", "fallback"


def _keyword_completion(answer: str, expect_keywords: List[str]) -> bool:
    answer = (answer or "").strip()
    if not answer:
        return False
    return all(kw in answer for kw in expect_keywords)


def llm_judge_case(
    case: dict,
    obs: Dict[str, Any],
    *,
    judge_fn: Optional[Callable[[dict, Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """对单个 case 做语义任务完成判定。

    ``judge_fn`` 可注入(mock 用,签名同本函数);默认走真实 LLM 调用。
    网络/解析失败时降级为关键词口径(确定性兜底),并标记 parse='fallback'。
    """
    if judge_fn is not None:
        try:
            return judge_fn(case, obs)
        except Exception as exc:
            answer = (obs.get("answer") or "").strip()
            return {
                "complete": _keyword_completion(answer, case.get("expect_keywords") or []),
                "reason": f"judge_fn 注入异常({type(exc).__name__}),已降级为关键词口径",
                "parse": "fallback",
            }
    from backend.core.rag.llm import chat_with_fallback

    answer = (obs.get("answer") or "").strip()
    messages = build_judge_messages(
        case["question"],
        case.get("expect_tools") or [],
        case.get("expect_keywords") or [],
        obs.get("tools_used") or [],
        answer,
    )
    try:
        content, _model, _reason = chat_with_fallback(
            messages,
            primary_model=JUDGE_MODEL,
            max_tokens=JUDGE_MAX_TOKENS,
            query_for_event=f"eval-judge:{case['question'][:40]}",
        )
        complete, reason, parse_mode = parse_judge_response(content)
        if parse_mode == "fallback":
            complete = _keyword_completion(answer, case.get("expect_keywords") or [])
        return {"complete": complete, "reason": reason, "parse": parse_mode}
    except Exception as exc:  # 网络/配额等:降级关键词口径,评测不中断
        return {
            "complete": _keyword_completion(answer, case.get("expect_keywords") or []),
            "reason": f"judge 调用失败({type(exc).__name__}),已降级为关键词口径",
            "parse": "fallback",
        }


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
    judge_mode: str = "keyword",
    judge_fn: Optional[Callable[[dict, Dict[str, Any]], Dict[str, Any]]] = None,
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
    # 任务完成:answer 非空 + keywords 全命中(keyword 口径)
    # 或 LLM 语义裁判判定(llm 口径,v2.2 T11)
    answer = (obs["answer"] or "").strip()
    judge: Dict[str, Any] = {}
    if not answer:
        failures.append("answer 为空")
    elif judge_mode == "llm":
        judge = llm_judge_case(case, obs, judge_fn=judge_fn)
        if not judge["complete"]:
            failures.append(f"judge 判定未完成: {judge['reason'][:120]}")
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
        "answer": answer,  # v2.2 T11:完整 answer 落结果,供 --input 复判
        "answer_preview": answer[:120],
    }
    if judge:
        meta["judge"] = judge
    return not failures, "; ".join(failures) or "ok", meta


def run_case(base_url: str, case: dict, max_steps: int, judge_mode: str = "keyword") -> tuple[bool, str]:
    ok, detail, _ = run_case_detailed(base_url, case, max_steps, judge_mode=judge_mode)
    return ok, detail


def run_evaluation(
    base_url: str = "http://127.0.0.1:8000",
    dataset_path: str = "tests/eval/golden-agent.jsonl",
    max_steps: int = 8,
    judge_mode: str = "keyword",
    judge_fn: Optional[Callable[[dict, Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """结构化执行入口(对齐 run_eval.py::run_evaluation),供 CLI 与未来 /api/eval 复用。"""
    started = datetime.now(timezone.utc)
    try:
        cases = load_dataset(dataset_path)
    except FileNotFoundError:
        return {"dataset": dataset_path, "total": 0, "passed": 0, "failed": 0,
                "pass_rate": 0.0, "duration_seconds": 0.0, "results": [],
                "timestamp": started.isoformat(), "base_url": base_url,
                "max_steps": max_steps, "judge_mode": judge_mode,
                "category_stats": {}, "latency_ms": {},
                "error": f"数据集不存在: {dataset_path}"}
    if not cases:
        return {"dataset": dataset_path, "total": 0, "passed": 0, "failed": 0,
                "pass_rate": 0.0, "duration_seconds": 0.0, "results": [],
                "timestamp": started.isoformat(), "base_url": base_url,
                "max_steps": max_steps, "judge_mode": judge_mode,
                "category_stats": {}, "latency_ms": {},
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
        ok, detail, meta = run_case_detailed(base_url, case, max_steps, judge_mode=judge_mode, judge_fn=judge_fn)
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
            "answer": meta["answer"],
            "answer_preview": meta["answer_preview"],
            "judge": meta.get("judge"),
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
        # 任务完成率(answer 非空 + keywords 命中 / judge 判定;对 error case 记为失败)
        if judge_mode == "llm":
            answer_ok = bool(meta["judge"].get("complete") if meta.get("judge") else False)
        else:
            answer_ok = bool((meta["answer"] or "").strip()) and all(
                kw in meta["answer"] for kw in (case.get("expect_keywords") or [])
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
        "judge_mode": judge_mode,
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


def rejudge_result(
    input_path: str,
    judge_mode: str = "llm",
    judge_fn: Optional[Callable[[dict, Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """v2.2 T11:读取已保存的评测结果 JSON,不重跑 Agent,仅用指定口径复判。

    输入须为 run_evaluation() 的输出结构且每条含完整 ``answer`` 字段
    (v2.2 起落库/落盘的结果均含;v2.1.0 及更早只有 answer_preview,无法复判)。
    输出:原结果 + judge 口径的任务完成率 + 每条 ``judge`` 判定。
    """
    with open(input_path, encoding="utf-8") as f:
        saved = json.load(f)
    judge_ok = 0
    judge_total = 0
    judge_details: List[Dict[str, Any]] = []
    for r in saved.get("results") or []:
        answer = (r.get("answer") or "").strip()
        if not answer:
            answer = r.get("answer_preview") or ""
        case = {
            "question": r["question"],
            "expect_tools": r.get("expect_tools") or [],
            "expect_keywords": r.get("expect_keywords") or [],
        }
        obs = {
            "answer": answer,
            "tools_used": r.get("tools_used") or [],
        }
        judge = llm_judge_case(case, obs, judge_fn=judge_fn)
        r["judge"] = judge
        judge_details.append({
            "question": r["question"],
            "category": r.get("category"),
            "original_ok": r.get("ok"),
            "judge_complete": judge["complete"],
            "judge_reason": judge["reason"],
            "judge_parse": judge["parse"],
        })
        judge_total += 1
        if judge["complete"]:
            judge_ok += 1
    out = dict(saved)
    out["judge_mode"] = judge_mode
    out["rejudged"] = True
    out["rejudge_input"] = input_path
    out["rejudge_task_completion_rate"] = round(judge_ok / judge_total, 4) if judge_total else 0.0
    out["rejudge_summary"] = {
        "judged": judge_total,
        "complete": judge_ok,
        "incomplete": judge_total - judge_ok,
        "parse_fallback": sum(1 for j in judge_details if j["judge_parse"] == "fallback"),
    }
    out["judge_details"] = judge_details
    return out


def estimate_cost_yuan(total_in: int, total_out: int) -> float:
    """按阿里云百炼刊例价估算单次评测成本(元)。

    单价与 scripts/lib/CostLog-Rotate.ps1 的 $priceTable 同源
    (qwen3.6-plus 输入 4.0 元/M、输出 12.0 元/M;qwen3.7-max 12/36)。
    仅量级参考;真实成本以 cost_log.jsonl + cost-alert.ps1 rollup 为准。
    """
    in_cost = (total_in or 0) / 1_000_000.0 * 4.0
    out_cost = (total_out or 0) / 1_000_000.0 * 12.0
    return round(in_cost + out_cost, 3)


def _default_run_id(judge_mode: str, rejudge: bool = False) -> str:
    """确定性 run_id:同口径同日幂等覆盖;复判带 -rejudge 后缀。"""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    suffix = "-rejudge" if rejudge else ""
    return f"agent-{judge_mode}-{date}{suffix}"


def main() -> int:
    ap = argparse.ArgumentParser(description="KB-AI Agent 评测(工具选择 + 任务完成)")
    ap.add_argument("--dataset", default="tests/eval/golden-agent.jsonl")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--max-steps", type=int, default=8)
    ap.add_argument(
        "--judge", choices=["keyword", "llm"], default="keyword",
        help="任务完成判定口径:keyword=关键词字面子串(确定性/零成本/CI 可用,默认);"
             "llm=LLM 语义裁判(v2.2 T11,额外 ~23 次 judge 调用)",
    )
    ap.add_argument(
        "--input", metavar="PATH", default=None,
        help="跳过 Agent 实跑,读取已保存的评测结果 JSON(须含完整 answer 字段)"
             "并用指定口径复判任务完成率",
    )
    ap.add_argument(
        "--no-persist", action="store_true",
        help="不写 eval_runs 表(默认落库,同口径同日重跑幂等覆盖)",
    )
    ap.add_argument("--run-id", default=None, help="eval_runs 行 ID(默认 agent-<口径>-<日期>)")
    ap.add_argument("--json", action="store_true", help="只输出 JSON 结果(供 CI/脚本消费)")
    args = ap.parse_args()

    try:
        if args.input:
            result = rejudge_result(args.input, judge_mode=args.judge)
        else:
            cases = load_dataset(args.dataset)
            if not cases:
                print(f"[ERROR] 数据集为空: {args.dataset}")
                return 1
    except FileNotFoundError:
        print(f"[ERROR] 数据集不存在: {args.input or args.dataset}")
        return 1

    if not args.json:
        if args.input:
            print(f"复判输入: {args.input}({len(result.get('results') or [])} 条,不重跑 Agent)")
        else:
            print(f"数据集: {args.dataset}({len(result.get('results') or [])} 条)")
            print(f"端点:   {args.base_url}/api/agent/chat (max_steps={args.max_steps})")
        print(f"口径:   {args.judge}")
        print("-" * 64)

    if not args.input:
        try:
            result = run_evaluation(args.base_url, args.dataset, args.max_steps, judge_mode=args.judge)
        except urllib.error.URLError as exc:
            print(f"[ERROR] 后端不可达({exc});请先启动后端与 Qdrant")
            return 2

    run_id = args.run_id or _default_run_id(args.judge, rejudge=bool(args.input))
    results_all = result.get("results") or []
    est_in = sum(r.get("total_in") or 0 for r in results_all)
    est_out = sum(r.get("total_out") or 0 for r in results_all)
    cost_estimate = estimate_cost_yuan(est_in, est_out) if not args.input else None
    if not args.no_persist:
        try:
            from backend.core.sqlite.eval_repo import save_eval_run
            save_eval_run(
                run_id,
                kind="agent",
                mode=args.judge,
                result=result,
                cost_estimate_yuan=cost_estimate,
            )
        except Exception as exc:
            print(f"[WARN] eval_runs 落库失败(不影响评测结果): {exc!r}")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("failed", 0) == 0 else 1

    if args.input:
        summary = result.get("rejudge_summary") or {}
        print(f"复判完成率({args.judge} 口径): "
              f"{result.get('rejudge_task_completion_rate')} "
              f"({summary.get('complete')}/{summary.get('judged')}, "
              f"解析降级 {summary.get('parse_fallback')} 条)")
        print(f"对比原关键词口径完成率: {result.get('task_completion_rate')}")
        for j in result.get("judge_details") or []:
            mark = "PASS" if j["judge_complete"] else "FAIL"
            print(f"[{mark}] {j['question'][:40]}")
            if not j["judge_complete"]:
                print(f"       原因: {j['judge_reason'][:120]}")
    else:
        for i, r in enumerate(result["results"], 1):
            mark = "PASS" if r["ok"] else "FAIL"
            print(f"[{mark}] #{i} [{r['category']}] {r['question'][:36]}")
            print(f"       工具={r['tools_used'] or '无'} 步数={r['steps']} "
                  f"耗时={r['elapsed_ms']}ms tokens={r['total_in'] + r['total_out']}")
            if not r["ok"]:
                print(f"       原因: {r['detail']}")
    print("-" * 64)
    if args.input:
        print(f"复判口径任务完成率: {result['rejudge_task_completion_rate']} | "
              f"原始口径任务完成率: {result.get('task_completion_rate')}")
    else:
        print(f"通过: {result['passed']}/{result['total']} (pass_rate={result['pass_rate']})")
        print(f"工具选择准确率: {result['tools_accuracy']} | "
              f"任务完成率: {result['task_completion_rate']} | "
              f"平均步数: {result['avg_steps']}")
        print(f"p95 延迟: {result['latency_ms']['p95']}ms | "
              f"总 tokens: {result['total_tokens']} | "
              f"每任务 tokens: {result['avg_tokens_per_task']} | "
              f"估算成本: ¥{cost_estimate}")
    print(f"eval_runs 落库: {'跳过(--no-persist)' if args.no_persist else run_id}")
    return 0 if result.get("failed", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
