"""Cost-alert 后端逻辑单测 (v1.3.0)。

覆盖:
  - _post_chat 返回 (content, usage) tuple
  - _log_token_usage atomic_append 到 data/cost_log.jsonl
  - chat_with_fallback 成功路径调用 _log_token_usage
  - _post_chat_stream 尾部 yield {"type": "usage", ...}
  - 非法/缺失 usage → 不崩,调用方决策
  - 多种 usage 字段名归一(input_tokens/prompt_tokens 等)
"""
import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """把 data/ 路径指向 tmp_path。"""
    monkeypatch.setattr("backend.core.config.get_data_dir", lambda: tmp_path)
    return tmp_path


def test_post_chat_returns_usage_dict(tmp_data_dir):
    """_post_chat 应返回 (content, usage) 元组,usage 含 input/output_tokens。"""
    from backend.core.rag.llm import _post_chat

    fake_response = {
        "choices": [{"message": {"content": "hi"}}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    with patch("backend.core.rag.llm.urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(fake_response).encode("utf-8")
        mock_resp.__enter__ = lambda self: self
        mock_resp.__exit__ = lambda self, *a: None
        mock_urlopen.return_value = mock_resp

        content, usage = _post_chat("fake_key", "qwen3.6-plus", [{"role": "user", "content": "hi"}])

    assert content == "hi"
    assert usage == {"input_tokens": 10, "output_tokens": 5}


def test_post_chat_usage_none_when_absent(tmp_data_dir):
    """_post_chat 在 API 不返回 usage 字段时,usage 应为 None(由调用方决定)。"""
    from backend.core.rag.llm import _post_chat

    fake_response = {
        "choices": [{"message": {"content": "hi"}}],
        # 无 usage 字段
    }
    with patch("backend.core.rag.llm.urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(fake_response).encode("utf-8")
        mock_resp.__enter__ = lambda self: self
        mock_resp.__exit__ = lambda self, *a: None
        mock_urlopen.return_value = mock_resp

        content, usage = _post_chat("fake_key", "qwen3.6-plus", [{"role": "user", "content": "hi"}])

    assert content == "hi"
    assert usage is None


def test_log_token_usage_appends_to_cost_log(tmp_data_dir):
    """_log_token_usage 应原子追加一行到 data/cost_log.jsonl。"""
    from backend.core.rag.llm import _log_token_usage

    _log_token_usage("qwen3.6-plus", 100, 50)

    log_file = tmp_data_dir / "cost_log.jsonl"
    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["model"] == "qwen3.6-plus"
    assert entry["in"] == 100
    assert entry["out"] == 50
    assert "ts" in entry  # ISO8601
    assert "cost_yuan" not in entry  # 不在 log 时算


def test_chat_with_fallback_logs_usage(tmp_data_dir):
    """chat_with_fallback 应在成功后调用 _log_token_usage。"""
    from backend.core.rag import llm

    with patch.object(llm, "_post_chat", return_value=("hi", {"input_tokens": 20, "output_tokens": 10})):
        with patch.object(llm, "_log_token_usage") as mock_log:
            llm.chat_with_fallback(api_key="fake", primary_model="qwen3.6-plus",
                                   messages=[{"role": "user", "content": "hi"}])

    mock_log.assert_called_once()
    args, kwargs = mock_log.call_args
    # args=(model, input, output)
    assert args[0] == "qwen3.6-plus"
    assert args[1] == 20
    assert args[2] == 10


def test_chat_with_fallback_skips_log_when_usage_none(tmp_data_dir):
    """API 不返回 usage 时,chat_with_fallback 不应抛错也不记录。"""
    from backend.core.rag import llm

    with patch.object(llm, "_post_chat", return_value=("hi", None)):
        with patch.object(llm, "_log_token_usage") as mock_log:
            llm.chat_with_fallback(api_key="fake", primary_model="qwen3.6-plus",
                                   messages=[{"role": "user", "content": "hi"}])

    mock_log.assert_not_called()


def test_post_chat_stream_yields_usage_at_end(tmp_data_dir):
    """_post_chat_stream 最后一段 delta 应包含 usage 信息。"""
    from backend.core.rag.llm import _post_chat_stream

    # 模拟 OpenAI 兼容 streaming 响应:
    # data: {"choices":[{"delta":{"content":"hi"}}]}
    # data: {"choices":[{"delta":{}}], "usage":{"input_tokens":15,"output_tokens":3}}
    # data: [DONE]
    chunks = [
        b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n',
        b'data: {"choices":[{"delta":{}}], "usage":{"input_tokens":15,"output_tokens":3}}\n\n',
        b'data: [DONE]\n\n',
    ]

    class FakeResp:
        def __init__(self):
            self._chunks = list(chunks)
        def read(self, n=-1):
            if not self._chunks:
                return b""
            return self._chunks.pop(0)
        def readline(self):
            return self.read()
        def __iter__(self):
            return iter(self._chunks)
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return None

    with patch("backend.core.rag.llm.urllib.request.urlopen", return_value=FakeResp()):
        events = list(_post_chat_stream("fake_key", "qwen3.6-plus",
                                         [{"role": "user", "content": "hi"}]))

    # 期望:每个事件是 dict,含 type
    types = [e["type"] for e in events]
    assert "delta" in types
    assert "usage" in types
    usage_events = [e for e in events if e["type"] == "usage"]
    assert len(usage_events) == 1
    assert usage_events[0]["input_tokens"] == 15
    assert usage_events[0]["output_tokens"] == 3
