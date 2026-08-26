"""Dashboard cost-alert 字段单测 (v1.3.0)。

覆盖:
  - _read_cost_alert 从 health_status.json.cost_alert 读取,容错 (文件缺失/JSON 损坏)
  - _build_overview 包含 cost_alert 字段
  - 默认值(level=0)在文件缺失 / JSON 损坏时生效
"""
import json
from unittest.mock import patch

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """把 data/ 路径指向 tmp_path(在 dashboard 模块的命名空间里 patch)。"""
    from backend.api import dashboard
    monkeypatch.setattr(dashboard, "get_data_dir", lambda: tmp_path)
    return tmp_path


def test_overview_includes_cost_alert(tmp_data_dir):
    """_build_overview 应返回包含 cost_alert 字段的 dict。"""
    from backend.api import dashboard

    health = {
        "cost_alert": {
            "level": 1,
            "today_yuan": 250.0,
            "month_yuan": 250.0,
            "thresholds": {"warn": 500, "high": 1000, "block": 1500},
        }
    }
    (tmp_data_dir / "health_status.json").write_text(
        json.dumps(health), encoding="utf-8"
    )

    # 抑制真实 IO(health_summary / kb_stats 等)
    with patch.object(dashboard, "_health_summary", return_value={}), \
         patch.object(dashboard, "_degradations_summary", return_value={}), \
         patch.object(dashboard, "_kb_stats", return_value={}), \
         patch.object(dashboard, "_drift_check", return_value={}), \
         patch.object(dashboard, "_system_info", return_value={}):
        overview = dashboard._build_overview()

    assert "cost_alert" in overview
    assert overview["cost_alert"]["level"] == 1
    assert overview["cost_alert"]["month_yuan"] == 250.0


def test_read_cost_alert_returns_default_when_file_missing(tmp_data_dir):
    """health_status.json 不存在时,_read_cost_alert 应返回默认 level=0。"""
    from backend.api import dashboard

    # 不写文件
    assert not (tmp_data_dir / "health_status.json").exists()

    ca = dashboard._read_cost_alert()
    assert ca["level"] == 0
    assert ca["today_yuan"] == 0.0
    assert ca["month_yuan"] == 0.0
    # 默认值应包含 sentinel 空字符串(前端检测用)
    assert ca["month"] == ""
    assert ca["updated_at"] == ""
    # 默认阈值应存在
    assert ca["thresholds"]["warn"] == 500
    assert ca["thresholds"]["high"] == 1000
    assert ca["thresholds"]["block"] == 1500


def test_read_cost_alert_returns_default_when_json_broken(tmp_data_dir):
    """health_status.json JSON 损坏时,_read_cost_alert 应返回默认 level=0。"""
    from backend.api import dashboard

    (tmp_data_dir / "health_status.json").write_text("{invalid json", encoding="utf-8")

    ca = dashboard._read_cost_alert()
    assert ca["level"] == 0
    assert ca["thresholds"]["block"] == 1500


def test_read_cost_alert_returns_default_when_field_missing(tmp_data_dir):
    """health_status.json 存在但无 cost_alert 字段时,应返回默认 level=0。"""
    from backend.api import dashboard

    (tmp_data_dir / "health_status.json").write_text(
        json.dumps({"other_field": "x"}), encoding="utf-8"
    )

    ca = dashboard._read_cost_alert()
    assert ca["level"] == 0
    assert ca["thresholds"]["block"] == 1500


def test_read_cost_alert_returns_default_when_field_wrong_type(tmp_data_dir):
    """health_status.json.cost_alert 不是 dict 时,应返回默认 level=0。"""
    from backend.api import dashboard

    (tmp_data_dir / "health_status.json").write_text(
        json.dumps({"cost_alert": "oops"}), encoding="utf-8"
    )

    ca = dashboard._read_cost_alert()
    assert ca["level"] == 0
    assert ca["thresholds"]["block"] == 1500


def test_read_cost_alert_reads_real_data(tmp_data_dir):
    """正常情况:从 health_status.json.cost_alert 读取并透传。"""
    from backend.api import dashboard

    health = {
        "cost_alert": {
            "level": 2,
            "today_yuan": 800.0,
            "month_yuan": 1100.0,
            "thresholds": {"warn": 500, "high": 1000, "block": 1500},
            "month": "2026-07",
        }
    }
    (tmp_data_dir / "health_status.json").write_text(
        json.dumps(health), encoding="utf-8"
    )

    ca = dashboard._read_cost_alert()
    assert ca["level"] == 2
    assert ca["month_yuan"] == 1100.0
    assert ca["month"] == "2026-07"
