"""extract_streaming_content 单测(v0.8.7 流式输出配套)。"""
from backend.core.rag.llm import extract_streaming_content


def test_complete_json_answer():
    raw = '{"type":"answer","content":"你好[1]，世界。","citations":[1]}'
    assert extract_streaming_content(raw) == "你好[1]，世界。"


def test_partial_json_answer():
    raw = '{"type":"answer","content":"你好，流式'
    assert extract_streaming_content(raw) == "你好，流式"


def test_code_fence_prefix():
    raw = '```json\n{"type":"answer","content":"带围栏的正文'
    assert extract_streaming_content(raw) == "带围栏的正文"


def test_escapes_unescaped():
    raw = '{"type":"answer","content":"第一行\\n第二行 \\"引号\\"'
    assert extract_streaming_content(raw) == '第一行\n第二行 "引号"'


def test_incomplete_escape_waits():
    # 结尾是半个转义:不应输出反斜杠,等下一 delta
    raw = '{"type":"answer","content":"abc\\'
    assert extract_streaming_content(raw) == "abc"


def test_incomplete_unicode_waits():
    raw = '{"type":"answer","content":"abc\\u4f'
    assert extract_streaming_content(raw) == "abc"


def test_clarify_returns_empty():
    raw = '{"type":"clarify","question":"您想问哪家门店?"}'
    assert extract_streaming_content(raw) == ""


def test_surrogate_pair_waits():
    # emoji 的 UTF-16 代理对只来了一半:安全截断
    raw = '{"type":"answer","content":"ok\\ud83d'
    assert extract_streaming_content(raw) == "ok"


def test_empty_and_garbage():
    assert extract_streaming_content("") == ""
    assert extract_streaming_content("{") == ""
