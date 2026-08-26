"""cost_alert_guard.py helper 单元测试 (v1.3.1)。

覆盖 safe_get_usage_tokens 防御性解析 + validate_cost_alert_payload 字段校验。
"""
from __future__ import annotations

from backend.core.cost_alert_guard import safe_get_usage_tokens


# ---- safe_get_usage_tokens ----

def test_safe_get_usage_tokens_none():
    """usage 为 None → 返回 None。"""
    assert safe_get_usage_tokens(None) is None


def test_safe_get_usage_tokens_non_mapping_string():
    """usage 为非 Mapping(字符串) → 返回 None。"""
    assert safe_get_usage_tokens("invalid") is None


def test_safe_get_usage_tokens_empty_dict():
    """usage 为 {} → 返回 None(所有字段都缺)。"""
    assert safe_get_usage_tokens({}) is None


def test_safe_get_usage_tokens_dashscope_full():
    """DashScope-style 完整字段。"""
    result = safe_get_usage_tokens({"input_tokens": 100, "output_tokens": 50})
    assert result == {"input_tokens": 100, "output_tokens": 50}


def test_safe_get_usage_tokens_openai_full():
    """OpenAI-style 完整字段(prompt_tokens / completion_tokens)。"""
    result = safe_get_usage_tokens({"prompt_tokens": 200, "completion_tokens": 80})
    assert result == {"input_tokens": 200, "output_tokens": 80}


def test_safe_get_usage_tokens_partial_fields():
    """只给 input_tokens → output_tokens 填 0(允许 None → 0)。"""
    result = safe_get_usage_tokens({"input_tokens": 100})
    assert result == {"input_tokens": 100, "output_tokens": 0}


def test_safe_get_usage_tokens_mixed_invalid_string_and_valid():
    """字符串字段 "abc" 无效 → 该字段 0;另一字段有效 → 取该值。"""
    result = safe_get_usage_tokens(
        {"prompt_tokens": "abc", "completion_tokens": 50}
    )
    assert result == {"input_tokens": 0, "output_tokens": 50}


def test_safe_get_usage_tokens_numeric_string():
    """字符串数字 "100" → int("100") = 100。"""
    result = safe_get_usage_tokens({"input_tokens": "100"})
    assert result == {"input_tokens": 100, "output_tokens": 0}


# ---- validate_cost_alert_payload (Task 3) ----

from backend.core.cost_alert_guard import validate_cost_alert_payload, DEFAULT_COST_ALERT  # noqa: E402


def test_validate_cost_alert_payload_none():
    """None → DEFAULT_COST_ALERT 拷贝。"""
    result = validate_cost_alert_payload(None)
    assert result["level"] == DEFAULT_COST_ALERT["level"]
    assert result["month_yuan"] == DEFAULT_COST_ALERT["month_yuan"]
    assert result["thresholds"]["block"] == DEFAULT_COST_ALERT["thresholds"]["block"]


def test_validate_cost_alert_payload_empty_dict():
    """{} → DEFAULT_COST_ALERT 拷贝。"""
    result = validate_cost_alert_payload({})
    assert result["level"] == 0
    assert result["today_yuan"] == 0.0
    assert result["month"] == ""


def test_validate_cost_alert_payload_level_string():
    """level="3"(字符串) → 降级 0。"""
    result = validate_cost_alert_payload({"level": "3"})
    assert result["level"] == 0


def test_validate_cost_alert_payload_level_out_of_range():
    """level=99 → 降级 0(超出 0-3 范围)。"""
    result = validate_cost_alert_payload({"level": 99})
    assert result["level"] == 0


def test_validate_cost_alert_payload_thresholds_null():
    """thresholds=null → 用 DEFAULT_COST_ALERT.thresholds。"""
    result = validate_cost_alert_payload({"level": 2, "thresholds": None})
    assert result["level"] == 2
    assert result["thresholds"] == {"warn": 500.0, "high": 1000.0, "block": 1500.0}


def test_validate_cost_alert_payload_negative_month_yuan():
    """month_yuan=-5(负数) → 降级 0.0。"""
    result = validate_cost_alert_payload({"level": 2, "month_yuan": -5})
    assert result["level"] == 2
    assert result["month_yuan"] == 0.0


def test_validate_cost_alert_payload_partial_invalid_thresholds():
    """thresholds.warn="abc" → 该字段降级 500.0,其他保留。"""
    result = validate_cost_alert_payload(
        {"level": 2, "thresholds": {"warn": "abc", "high": 800, "block": 1200}}
    )
    assert result["level"] == 2
    assert result["thresholds"]["warn"] == 500.0  # 无效 → 默认
    assert result["thresholds"]["high"] == 800.0
    assert result["thresholds"]["block"] == 1200.0
