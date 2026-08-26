from datetime import date, datetime, timezone

from backend.core.rag.metadata import (
    build_chunk_metadata,
    calculate_days_old,
    calculate_temporal_weight,
    classify_certainty,
    extract_frontmatter,
    resolve_document_date,
)


def test_extract_simple_frontmatter_and_body():
    meta, body = extract_frontmatter(
        "---\ndate: 2026-07-01\ncertainty: fact\ntags: [menu]\n---\n# 标题\n正文"
    )
    assert meta["date"] == "2026-07-01"
    assert meta["certainty"] == "fact"
    assert body == "# 标题\n正文"


def test_non_frontmatter_text_is_unchanged():
    text = "# 标题\n正文"
    assert extract_frontmatter(text) == ({}, text)


def test_invalid_frontmatter_does_not_drop_document():
    text = "---\nnot-a-key-line\n---\n正文"
    meta, body = extract_frontmatter(text)
    assert meta == {}
    assert body == "正文"


def test_unclosed_frontmatter_is_unchanged():
    text = "---\ndate: 2026-07-01\n正文"
    assert extract_frontmatter(text) == ({}, text)


def test_date_prefers_updated_then_date_then_mtime():
    today = date(2026, 7, 20)
    assert (
        resolve_document_date(
            {"updated": "2026-07-18", "date": "2026-07-01"}, today=today
        )
        == "2026-07-18"
    )
    assert resolve_document_date({"date": "2026-07-01"}, today=today) == "2026-07-01"
    mtime = datetime(2026, 6, 20, tzinfo=timezone.utc).timestamp()
    assert resolve_document_date({}, file_mtime=mtime, today=today) == "2026-06-20"


def test_date_uses_created_after_invalid_newer_fields():
    assert (
        resolve_document_date(
            {"updated": "invalid", "date": "", "created": "2026-05-10"}
        )
        == "2026-05-10"
    )


def test_days_old_and_temporal_weight_are_bounded():
    assert calculate_days_old("2026-07-18", today=date(2026, 7, 20)) == 2
    assert calculate_days_old("not-a-date", today=date(2026, 7, 20)) is None
    assert calculate_temporal_weight(None) == 1.0
    assert calculate_temporal_weight(0) == 1.0
    assert calculate_temporal_weight(365) == 0.367879
    assert calculate_temporal_weight(10000) == 0.1


def test_future_date_and_invalid_half_life_keep_full_weight():
    assert calculate_days_old("2026-07-21", today=date(2026, 7, 20)) == 0
    assert calculate_temporal_weight(10, half_life_days=0) == 1.0


def test_certainty_rules_match_existing_categories():
    assert classify_certainty("") == "draft"
    assert classify_certainty("TODO 待确认") == "draft"
    assert (
        classify_certainty(
            "2026年营收增长12%，新增会员300人，本季度经营数据已经完成核对并归档。"
        )
        == "fact"
    )
    assert (
        classify_certainty(
            "建议优先优化储值激励，应该加强培训，同时需要安排负责人跟进执行。"
        )
        == "opinion"
    )
    assert (
        classify_certainty(
            "这是一段没有明显信号的说明文字，内容足够长并且只用于描述一般背景，不包含明确判断。"
        )
        == "neutral"
    )


def test_build_chunk_metadata_uses_document_date():
    metadata = build_chunk_metadata(
        "建议优先优化储值激励，应该加强培训，同时需要安排负责人跟进执行。",
        document_date="2026-07-18",
        today=date(2026, 7, 20),
    )

    assert metadata == {
        "date": "2026-07-18",
        "days_old": 2,
        "temporal_weight": 0.994536,
        "certainty": "opinion",
    }


def test_build_chunk_metadata_falls_back_to_utc_mtime():
    mtime = datetime(2026, 6, 20, tzinfo=timezone.utc).timestamp()

    metadata = build_chunk_metadata(
        "这是一段没有明显信号的说明文字，内容足够长并且只用于描述一般背景，不包含明确判断。",
        document_mtime=mtime,
        today=date(2026, 7, 20),
    )

    assert metadata == {
        "date": "2026-06-20",
        "days_old": 30,
        "temporal_weight": 0.921095,
        "certainty": "neutral",
    }
