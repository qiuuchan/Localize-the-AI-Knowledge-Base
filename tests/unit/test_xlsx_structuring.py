import sys
from types import SimpleNamespace

from backend.core.rag import mineru


class FakeWorksheet:
    title = "门店进度"

    def iter_rows(self, values_only=True):
        assert values_only is True
        return iter(
            [
                ("姓名", "门店", "进度", "日期"),
                ("张三", "一店", "完成", "2026-06-30"),
                (None, None, None, None),
                ("李四", "二店", "待确认", None),
            ]
        )


class FakeWorkbook:
    worksheets = [FakeWorksheet()]


def test_format_xlsx_sheet_emits_header_and_key_value_rows():
    text = mineru.format_xlsx_sheet(
        "门店进度",
        [
            ("姓名", "门店", "进度"),
            ("张三", "一店", "完成"),
        ],
    )

    assert "# 工作表：门店进度" in text
    assert "表头：姓名 | 门店 | 进度" in text
    assert "第 2 行：姓名=张三；门店=一店；进度=完成" in text
    assert "None" not in text


def test_format_xlsx_sheet_skips_empty_rows_and_uses_column_labels():
    text = mineru.format_xlsx_sheet(
        "空表",
        [
            (None, None),
            ("", ""),
        ],
    )

    assert text == ""


def test_format_xlsx_sheet_fills_missing_header_with_column_label():
    text = mineru.format_xlsx_sheet(
        "测试",
        [
            ("姓名", None, "进度"),
            ("张三", "一店", "完成"),
        ],
    )

    assert "表头：姓名 | 列 B | 进度" in text
    assert "第 2 行：姓名=张三；列 B=一店；进度=完成" in text


def test_read_xlsx_uses_data_only_read_only(monkeypatch, tmp_path):
    calls = {}

    def load_workbook(path, data_only, read_only):
        calls.update(path=str(path), data_only=data_only, read_only=read_only)
        return FakeWorkbook()

    monkeypatch.setitem(
        sys.modules,
        "openpyxl",
        SimpleNamespace(load_workbook=load_workbook),
    )
    path = tmp_path / "progress.xlsx"
    path.write_bytes(b"xlsx")

    text = mineru._read_xlsx(path)

    assert "工作表：门店进度" in text
    assert calls["data_only"] is True
    assert calls["read_only"] is True
