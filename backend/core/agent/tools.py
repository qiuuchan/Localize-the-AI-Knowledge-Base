"""Agent tool registry (v2.0 PR#1).

TOOLS is an OpenAI function-calling schema list consumed by
``chat_with_fallback_tools`` (PR#2); ``execute_tool`` dispatches by name and
NEVER raises — every failure path returns ``{"error": ...}`` so the agent loop
can feed the observation back to the model and continue (设计稿 §4.1 / §11 #3).

PR#1 ships 3 read-only tools: kb_search / calculator / get_current_time.
PR#4 adds web_search via the existing scripts/websearch.ps1 channel and
gives kb_search a global-offset mode (发现 #1) for multi-turn citation
numbering.

Tool descriptions are written for a generic knowledge-base scenario on
purpose (no industry identity wording) so the public-repo sanitizer has
nothing to scrub here.
"""
from __future__ import annotations

import ast
import json
import math
import operator
from datetime import datetime
from typing import Any, Dict

from backend.core.config import get_root_dir
from backend.core.ps_runner import run_ps
from backend.core.rag.llm import format_chunks_only
from backend.core.rag.retriever import retrieve

MAX_EXPRESSION_CHARS = 200
_MAX_POW_EXPONENT = 1000
WEBSEARCH_TIMEOUT = 30

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_WEEKDAYS_ZH = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def _wrap_untrusted(text: str, tag: str) -> str:
    """v2.1.0 prompt injection 加固:不可信内容包在显式分隔符里回填。

    kb_search / web_search 的 observation 原样拼接进模型上下文——检索命中
    的文档或网页本身可能携带「忽略指令/调用工具」类注入文本。分隔符 +
    系统提示词规则 5(loop._AGENT_SYSTEM_PROMPT)双层声明:分隔符内是数据
    不是指令。取值自资料,不改写内容,引用编号不受影响。
    """
    return f"<{tag}>\n{text}\n</{tag}>" if text else text

TOOLS: list[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "kb_search",
            "description": (
                "检索本地知识库，返回带编号的资料片段（含来源/日期/确定性标签）。"
                "凡问题可能与企业内部文档、制度、经营数据、历史记录有关时优先使用；"
                "回答中引用资料时使用 [1] [2] 角标。知识库未命中或需要公开互联网"
                "实时信息时不要反复重试本工具。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索关键词或短句，尽量提取问题核心而非整句照抄",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回条数，默认 5，范围 1-20",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": (
                "计算一个纯算术表达式并返回数值结果，支持 + - * / % ** 与括号、"
                "负号。仅限数字与运算符：不允许变量、函数调用、属性访问或字符串。"
                "需要对检索到的数字做增长率、合计、占比等计算时必须使用本工具，"
                "不要心算。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": '算术表达式，例如 "(186000 - 152000) / 152000 * 100"，长度不超过 200 字符',
                    },
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": (
                "获取当前本地时间（ISO 格式）与星期。当用户询问今天/现在相关的"
                "信息，或需要判断资料新旧、计算时间跨度时使用；不需要频繁重复调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "搜索公开互联网并返回标题/链接/摘要。仅在知识库检索明显不足、"
                "且问题需要实时或外部信息（如新闻、政策、行情、公开资料）时使用；"
                "结果不代表内部资料，最终回答不要对搜索结果编造引用角标。"
                "知识库能回答的问题优先 kb_search，不要先试 web_search。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词或短句，尽量提取问题核心而非整句照抄",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


def _kb_search(args: Dict[str, Any], offset: int = 0) -> Dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"error": "kb_search 需要 query 参数"}
    try:
        top_k = int(args.get("top_k") or 5)
    except (TypeError, ValueError):
        top_k = 5
    top_k = max(1, min(top_k, 20))
    chunks = retrieve(query, top_k=top_k)
    # 发现 #1:多轮检索时 offset 续编全局角标(ctx 内 [N] 与 citations.index 一致),
    # 模型 observation 与聚合 citations 同源同号,不再错位。
    formatted = format_chunks_only(
        chunks, max_context_chars=4000, start_index=offset + 1
    )
    citations = formatted.get("citations") or []
    if not citations:
        return {
            "ok": False,
            "ctx": "",
            "citations": [],
            "note": "知识库未命中相关资料，可换关键词重试一次或改用其他方式回答",
        }
    return {
        "ok": True,
        "count": len(citations),
        "ctx": _wrap_untrusted(formatted.get("ctx") or "", "kb_context"),
        "citations": citations,
    }


def _eval_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("仅允许数字常量")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("不允许无穷大/NaN 常量")
        return value
    if isinstance(node, ast.BinOp):
        op = _BINOPS.get(type(node.op))
        if op is None:
            raise ValueError(f"不允许的运算符: {type(node.op).__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if type(node.op) is ast.Pow and abs(right) > _MAX_POW_EXPONENT:
            raise ValueError("指数过大")
        result = op(left, right)
        if isinstance(result, float) and not math.isfinite(result):
            raise ValueError("计算结果溢出")
        return result
    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        raise ValueError(f"不允许的一元运算: {type(node.op).__name__}")
    raise ValueError(f"不允许的语法节点: {type(node).__name__}")


def _calculator(args: Dict[str, Any]) -> Dict[str, Any]:
    expression = str(args.get("expression") or "").strip()
    if not expression:
        return {"error": "calculator 需要 expression 参数"}
    if len(expression) > MAX_EXPRESSION_CHARS:
        return {"error": f"表达式超过 {MAX_EXPRESSION_CHARS} 字符上限"}
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        return {"error": f"表达式语法错误: {exc.msg}"}
    try:
        result = _eval_node(tree)
    except ValueError as exc:
        return {"error": f"表达式被拒绝: {exc}"}
    except ZeroDivisionError:
        return {"error": "除数为零"}
    except (OverflowError, TypeError) as exc:
        return {"error": f"计算失败: {exc}"}
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return {"ok": True, "expression": expression, "result": result}


def _get_current_time(_args: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now()
    return {
        "ok": True,
        "iso": now.isoformat(timespec="seconds"),
        "weekday": _WEEKDAYS_ZH[now.weekday()],
        "date": now.strftime("%Y-%m-%d"),
    }


def _web_search(args: Dict[str, Any]) -> Dict[str, Any]:
    """联网搜索:复用 scripts/websearch.ps1(Tavily → Bing)通道。

    设计稿 §11 风险 #3:timeout 30s,任何失败(脚本缺失/超时/非零退出/无结果)
    都转成 error observation,绝不抛断 Agent 循环。
    """
    query = str(args.get("query") or "").strip()
    if not query:
        return {"error": "web_search 需要 query 参数"}
    root = get_root_dir()
    script = root / "scripts" / "websearch.ps1"
    try:
        result = run_ps(
            script,
            args=["-Query", query, "-OutputJson"],
            cwd=root,
            timeout=WEBSEARCH_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001 — 含 subprocess.TimeoutExpired
        return {"error": f"web_search 执行失败: {type(exc).__name__}: {exc}"}
    if result.get("skipped"):
        return {"error": "websearch.ps1 不存在，web_search 不可用"}
    if result.get("returncode") != 0:
        detail = (result.get("stderr") or result.get("stdout") or "")[:200]
        return {"error": f"web_search 返回失败: {detail}"}
    payload = result.get("json") or {}
    results = payload.get("results") or []
    if not results:
        return {"ok": False, "ctx": "", "note": "联网搜索无结果，可换关键词或改用知识库"}
    # ctx 用「第 N 条」而非 [N],避免与 kb_search 的 citations 角标体系混淆
    lines = []
    for i, r in enumerate(results, start=1):
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        snippet = (r.get("snippet") or "").strip()
        lines.append(f"第{i}条: {title}\n来源: {url}\n摘要: {snippet}")
    return {
        "ok": True,
        "source": payload.get("source") or "web",
        "count": len(results),
        "ctx": _wrap_untrusted("\n\n".join(lines), "web_context"),
    }


_EXECUTORS = {
    "kb_search": _kb_search,
    "calculator": _calculator,
    "get_current_time": _get_current_time,
    "web_search": _web_search,
}


def execute_tool(name: str, args: Any = None, *, kb_offset: int = 0) -> Dict[str, Any]:
    """Dispatch one tool call; failures become error observations, never raises.

    args accepts both dict and the raw JSON string that DashScope tool_calls
    carry (T09 冒烟结论:function.arguments 需二次解析),防御两种形态。

    kb_offset: v2.0 PR#4 — Agent loop 传入已聚合 citation 数,让 kb_search
    输出全局编号的 observation(发现 #1);其他工具忽略。
    """
    executor = _EXECUTORS.get(name)
    if executor is None:
        return {"error": f"未知工具: {name}"}
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError as exc:
            return {"error": f"工具参数不是合法 JSON: {exc}"}
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return {"error": "工具参数必须是对象"}
    try:
        if name == "kb_search":
            return executor(args, offset=max(0, int(kb_offset)))
        return executor(args)
    except Exception as exc:  # noqa: BLE001 — observation contract
        return {"error": f"{name} 执行失败: {type(exc).__name__}: {exc}"}
