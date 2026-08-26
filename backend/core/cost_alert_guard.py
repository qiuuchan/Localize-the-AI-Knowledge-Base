"""v1.3.1: cost-alert 子系统防御性 helper。

两个函数:
  - safe_get_usage_tokens:防御性解析 LLM usage 字段(避免 AttributeError 误触发 fallback)
  - validate_cost_alert_payload:字段级校验 cost_alert dict(Task 3 实现)
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def safe_get_usage_tokens(usage: Any) -> Optional[dict[str, int]]:
    """Defensive extraction of input_tokens/output_tokens from LLM usage payload.

    兼容 DashScope-style {input_tokens, output_tokens} 与
    OpenAI-style {prompt_tokens, completion_tokens} 两种字段命名。

    规则:
      - usage is None 或非 Mapping → 返回 None
      - 任一字段值是合法非负 int(或可转 int 的字符串数字) → 该字段取该值
      - 任一字段值是其他类型(None / 浮点 / 非数字字符串 / 负数) → 该字段取 0
      - 所有字段都缺失或全部无效 → 返回 None

    返回值仅在"至少有一个字段是有效整数"时为 dict;否则 None。
    调用方对 None 走"跳过 cost 记录但不触发 LLM fallback"分支。
    """
    if usage is None or not isinstance(usage, Mapping):
        return None

    # 字段映射:(字段名列表, 目标键)
    candidates = [
        (("input_tokens", "prompt_tokens"), "input_tokens"),
        (("output_tokens", "completion_tokens"), "output_tokens"),
    ]

    result: dict[str, int] = {}
    has_any_valid = False

    for field_names, target_key in candidates:
        value = None
        for fname in field_names:
            if fname in usage:
                value = usage[fname]
                break
        if value is None:
            result[target_key] = 0
            continue
        # 尝试转 int
        if isinstance(value, bool):  # bool 是 int 子类,但语义非"token 数"
            result[target_key] = 0
            continue
        if isinstance(value, int):
            if value < 0:
                result[target_key] = 0
                continue
            result[target_key] = value
            has_any_valid = True
        elif isinstance(value, str):
            try:
                parsed = int(value)
                if parsed < 0:
                    result[target_key] = 0
                    continue
                result[target_key] = parsed
                has_any_valid = True
            except (ValueError, TypeError):
                result[target_key] = 0
        else:
            # float / None / 其他类型
            result[target_key] = 0

    if not has_any_valid:
        return None
    return result


# v1.3.1 (Task 3):字段级默认值 + validate_cost_alert_payload
# 警告:此 DEFAULT 与 `backend/api/dashboard.py:_COST_ALERT_DEFAULT` 数值阈值同步
# (warn=500/high=1000/block=1500),见 spec §2.4 + §1.3 invariant #8。
DEFAULT_COST_ALERT: Dict[str, Any] = {
    "level": 0,
    "today_yuan": 0.0,
    "month_yuan": 0.0,
    "month": "",
    "thresholds": {"warn": 500.0, "high": 1000.0, "block": 1500.0},
    "updated_at": "",
}


def validate_cost_alert_payload(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Field-level merge/validation of cost_alert payload.

    规则(每个字段独立降级到默认值,互不影响):
      - level: int 且 0 <= level <= 3 → 取该值;否则 → 0
      - today_yuan / month_yuan:数值(int/float)且 >= 0 → 取该值(转 float);否则 → 0.0
      - month / updated_at:字符串 → 原值;否则 → ""
      - thresholds: dict 且 warn/high/block 都是合法数值 → 取该值;
          任何字段非法或缺失 → 用 DEFAULT_COST_ALERT.thresholds 对应字段

    始终返回一个完整 dict(确保下游 chat.py / dashboard.py 调用字段不抛 KeyError)。
    """
    if raw is None or not isinstance(raw, dict):
        # 深拷贝,避免下游修改污染 DEFAULT
        import copy
        return copy.deepcopy(DEFAULT_COST_ALERT)

    result: Dict[str, Any] = {}

    # level
    lvl = raw.get("level", 0)
    if isinstance(lvl, int) and not isinstance(lvl, bool) and 0 <= lvl <= 3:
        result["level"] = lvl
    else:
        result["level"] = 0

    # today_yuan / month_yuan
    for yuan_key in ("today_yuan", "month_yuan"):
        v = raw.get(yuan_key, 0.0)
        if isinstance(v, bool):  # bool 是 int 子类
            result[yuan_key] = 0.0
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0:
            result[yuan_key] = float(v)
        else:
            result[yuan_key] = 0.0

    # month / updated_at
    for str_key in ("month", "updated_at"):
        v = raw.get(str_key, "")
        result[str_key] = v if isinstance(v, str) else ""

    # thresholds
    raw_thresh = raw.get("thresholds")
    default_thresh = DEFAULT_COST_ALERT["thresholds"]
    if isinstance(raw_thresh, dict):
        merged = {}
        for k in ("warn", "high", "block"):
            v = raw_thresh.get(k, default_thresh[k])
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                merged[k] = float(default_thresh[k])
            else:
                merged[k] = float(v)
        result["thresholds"] = merged
    else:
        import copy
        result["thresholds"] = copy.deepcopy(default_thresh)

    return result
