"""run_agent_eval judge 解析与口径单测 (v2.2 T11 — LLM-as-judge)。

覆盖(不触网):
  - parse_judge_response:纯 JSON / 代码围栏 / 前后杂文 / 非法 JSON 降级
  - llm_judge_case:judge_fn 注入(mock 裁判)→ 结果透传
  - llm_judge_case:judge_fn 抛异常 → 降级关键词口径(评测不中断)
  - rejudge_result:--input 复判流程(完整 answer → judge 判定 → 汇总)
"""
from __future__ import annotations

import json

from tests.eval.run_agent_eval import (
    build_judge_messages,
    llm_judge_case,
    parse_judge_response,
    rejudge_result,
)


# ---------------------------------------------------------------------------
# parse_judge_response 容错
# ---------------------------------------------------------------------------


def test_parse_plain_json():
    complete, reason, mode = parse_judge_response('{"complete": true, "reason": "答案完整"}')
    assert complete is True
    assert reason == "答案完整"
    assert mode == "json"


def test_parse_fenced_json():
    text = '```json\n{"complete": false, "reason": "缺少结果"}\n```'
    complete, reason, mode = parse_judge_response(text)
    assert complete is False
    assert mode == "json"


def test_parse_json_with_surrounding_text():
    text = '好的,我来判定:\n{"complete": true, "reason": "ok"}\n以上是结论。'
    complete, _, mode = parse_judge_response(text)
    assert complete is True
    assert mode == "json"


def test_parse_malformed_falls_back_to_keyword():
    complete, reason, mode = parse_judge_response("无法解析的回复")
    assert complete is False
    assert "非合法 JSON" in reason
    assert mode == "fallback"


def test_parse_empty_falls_back():
    complete, _, mode = parse_judge_response("")
    assert complete is False
    assert mode == "fallback"


# ---------------------------------------------------------------------------
# llm_judge_case:注入 judge_fn / 异常降级
# ---------------------------------------------------------------------------


def _case(**overrides) -> dict:
    case = {
        "question": "计算 128 乘以 46",
        "expect_tools": ["calculator"],
        "expect_keywords": ["5888"],
        "category": "calc_only",
    }
    case.update(overrides)
    return case


def test_judge_fn_passthrough():
    def fake_judge(case, obs):
        return {"complete": True, "reason": "mock", "parse": "json"}

    obs = {"answer": "128 乘以 46 等于 5888", "tools_used": ["calculator"]}
    judge = llm_judge_case(_case(), obs, judge_fn=fake_judge)
    assert judge == {"complete": True, "reason": "mock", "parse": "json"}


def test_judge_fn_exception_falls_back_to_keyword():
    def broken_judge(case, obs):
        raise RuntimeError("network down")

    # 关键词口径下:命中 → 降级判定为完成
    obs = {"answer": "128 乘以 46 等于 5888", "tools_used": ["calculator"]}
    judge = llm_judge_case(_case(), obs, judge_fn=broken_judge)
    assert judge["complete"] is True
    assert judge["parse"] == "fallback"

    # 关键词口径下:未命中 → 降级判定为未完成
    obs2 = {"answer": "答案是 5889", "tools_used": ["calculator"]}
    judge2 = llm_judge_case(_case(), obs2, judge_fn=broken_judge)
    assert judge2["complete"] is False
    assert judge2["parse"] == "fallback"


# ---------------------------------------------------------------------------
# build_judge_messages 结构
# ---------------------------------------------------------------------------


def test_build_judge_messages_shape():
    msgs = build_judge_messages("Q", ["calculator"], ["%"], ["calculator"], "22.37")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert "任务" in msgs[1]["content"]
    assert "%" in msgs[1]["content"]  # 期望要素传给裁判


# ---------------------------------------------------------------------------
# rejudge_result(--input 复判,judge_fn 注入)
# ---------------------------------------------------------------------------


def _saved_result_json(tmp_path) -> str:
    saved = {
        "dataset": "tests/eval/golden-agent.jsonl",
        "total": 2,
        "passed": 2,
        "failed": 0,
        "pass_rate": 1.0,
        "results": [
            {
                "question": "储值增长百分比是多少",
                "expect_tools": ["kb_search", "calculator"],
                "expect_keywords": ["%"],
                "category": "multi_step_calc",
                "ok": False,  # 关键词口径假阴性
                "detail": "answer 缺少关键词 '%'",
                "tools_used": ["kb_search", "calculator"],
                "answer": "2026 年比 2025 年增长 22.37%,毛利率 37.5%。",
                "answer_preview": "2026 年比 2025 年增长 22.37%",
            },
            {
                "question": "今天是星期几",
                "expect_tools": ["get_current_time"],
                "expect_keywords": [],
                "category": "time_only",
                "ok": True,
                "detail": "ok",
                "tools_used": ["get_current_time"],
                "answer": "今天是 2026 年 9 月 1 日,星期二。",
                "answer_preview": "今天是 2026 年 9 月 1 日",
            },
        ],
        "task_completion_rate": 0.5,
        "tools_accuracy": 1.0,
        "timestamp": "2026-08-28T00:00:00+00:00",
    }
    p = tmp_path / "saved-result.json"
    p.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    return str(p)


def test_rejudge_result_with_mock_judge(tmp_path):
    def semantic_judge(case, obs):
        # 语义判定:无强制要素 → 完成;有强制要素 → 含"22.37"即完成
        # (不等价于字面 % —— 这正是 v210 假阴性的修复口径)
        if not case["expect_keywords"]:
            return {"complete": True, "reason": "mock", "parse": "json"}
        complete = "22.37" in obs.get("answer", "")
        return {"complete": complete, "reason": "mock", "parse": "json"}

    out = rejudge_result(_saved_result_json(tmp_path), judge_fn=semantic_judge)
    assert out["rejudged"] is True
    assert out["rejudge_task_completion_rate"] == 1.0  # 假阴性被纠正
    assert out["rejudge_summary"] == {"judged": 2, "complete": 2, "incomplete": 0, "parse_fallback": 0}
    # 每条 result 都带上了 judge 判定
    assert all("judge" in r for r in out["results"])
    assert out["judge_details"][0]["original_ok"] is False
    assert out["judge_details"][0]["judge_complete"] is True


def test_rejudge_result_counts_incomplete(tmp_path):
    def strict_judge(case, obs):
        return {"complete": False, "reason": "mock 判失败", "parse": "json"}

    out = rejudge_result(_saved_result_json(tmp_path), judge_fn=strict_judge)
    assert out["rejudge_task_completion_rate"] == 0.0
    assert out["rejudge_summary"]["complete"] == 0


def test_rejudge_result_empty_results(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text('{"results": []}', encoding="utf-8")
    out = rejudge_result(str(p), judge_fn=lambda c, o: {"complete": True, "reason": "x", "parse": "json"})
    assert out["rejudge_task_completion_rate"] == 0.0
    assert out["rejudge_summary"]["judged"] == 0
