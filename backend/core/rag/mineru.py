"""MinerU document parsing client + lightweight file type dispatch.

Mirrors scripts/parse-doc.ps1:
  - health_check(GET /health)
  - parse_pdf / parse_pptx (POST /file_parse with base64 body)
  - Plain text/markdown read directly
  - .docx falls back to pandoc; .xlsx falls back to openpyxl if installed.

Request body:
    {
      "file": "<base64 bytes>",
      "backend": "pipeline",
      "parse_method": "auto",
      "language": "ch"
    }

Response handling:
    result.md if present, else "\n".join(result.content list)
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from backend.core.config import get_env_or_env_var

DEFAULT_URL = "http://localhost:8001"
SIZE_LIMIT_BYTES = 200 * 1024 * 1024  # 200 MB safety cap

# Recognized extensions that benefit from mineru
_MINERU_EXTS = {".pdf", ".pptx"}
# Extensions handled directly without mineru
_PLAIN_EXTS = {".txt", ".md", ".markdown"}
# Extensions that need fallback tools
_PANDOC_EXTS = {".docx"}
_PYTHON_OPENPYXL_EXTS = {".xlsx"}


def _base_url(url: Optional[str]) -> str:
    return (url or get_env_or_env_var("MINERU_URL") or DEFAULT_URL).rstrip("/")


def health(url: Optional[str] = None) -> bool:
    """Check if MinerU is reachable."""
    try:
        req = urllib.request.Request(f"{_base_url(url)}/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _call_mineru(file_bytes: bytes, *, url: Optional[str] = None, timeout: int = 300) -> Dict[str, Any]:
    payload = {
        "file": base64.b64encode(file_bytes).decode("ascii"),
        "backend": "pipeline",
        "parse_method": "auto",
        "language": "ch",
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{_base_url(url)}/file_parse",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MinerU HTTP {e.code}: {detail[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"MinerU unreachable: {e}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"MinerU returned non-JSON: {raw[:200]}")


def _read_plain(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_pandoc(path: Path) -> str:
    if not shutil.which("pandoc"):
        raise RuntimeError(f"pandoc not installed; cannot convert {path.suffix}")
    out = subprocess.run(
        ["pandoc", str(path), "-t", "markdown", "--wrap=none"],
        capture_output=True,
        timeout=120,
    )
    if out.returncode != 0:
        raise RuntimeError(f"pandoc failed: {out.stderr.decode('utf-8', errors='replace')[:500]}")
    return out.stdout.decode("utf-8", errors="replace")


def _display_cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _column_label(index: int) -> str:
    value = index + 1
    letters = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return f"列 {letters}"


def format_xlsx_sheet(title: str, rows: list[tuple[object, ...]]) -> str:
    normalized = [[_display_cell(value) for value in row] for row in rows]
    non_empty = [row for row in normalized if any(row)]
    if not non_empty:
        return ""

    width = max(len(row) for row in non_empty)
    header = non_empty[0] + [""] * (width - len(non_empty[0]))
    headers = [value or _column_label(index) for index, value in enumerate(header)]
    output = [f"# 工作表：{title}", f"表头：{' | '.join(headers)}"]

    first_non_empty_idx = next(i for i, row in enumerate(normalized) if any(row))
    for raw_index, row in enumerate(normalized):
        if not any(row) or raw_index == first_non_empty_idx:
            continue
        cells = row + [""] * (width - len(row))
        fields = [
            f"{headers[i]}={cells[i]}" for i in range(width) if cells[i]
        ]
        if fields:
            output.append(f"第 {raw_index + 1} 行：{'；'.join(fields)}")
    return "\n\n".join(output)


def _read_xlsx(path: Path) -> str:
    try:
        import openpyxl  # type: ignore
    except ImportError as e:
        raise RuntimeError(f"openpyxl not installed; cannot read {path.suffix}: {e}")
    wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
    sheets: list[str] = []
    for ws in wb.worksheets:
        rows = [tuple(row) for row in ws.iter_rows(values_only=True)]
        text = format_xlsx_sheet(ws.title, rows)
        if text:
            sheets.append(text)
    return "\n\n".join(sheets)


def parse_to_markdown(
    path: Path,
    *,
    url: Optional[str] = None,
    use_cache: bool = True,
    cache_dir: Optional[Path] = None,
    doc_id: Optional[str] = None,
    db_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Parse a document file to markdown text.

    Returns {"markdown": str, "method": str, "cache_hit": bool}.
    Mirrors scripts/parse-doc.ps1:113-541 but simplified.

    v0.8.11(P2.2):cache_dir 按 `<db_id>/<doc_id>/` 分层,避免不同 db 的同名文件
    解析产物冲突。旧版扁平 `<cache_dir>/<doc_id>/` 路径仍可读(向后兼容),
    但新写入一律走新分层。
    """
    if not path.exists():
        raise FileNotFoundError(path)

    suffix = path.suffix.lower()
    size = path.stat().st_size
    if size > SIZE_LIMIT_BYTES:
        raise RuntimeError(
            f"{path.name} is {size // 1024 // 1024} MB, exceeds 200 MB safety cap"
        )

    # Cache key: doc_id (or filename) + mtime + size
    if doc_id is None:
        import hashlib
        doc_id = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]

    cache_path: Optional[Path] = None
    legacy_cache_path: Optional[Path] = None
    if use_cache and cache_dir is not None:
        # 新版分层路径:<db_id>/<doc_id>/raw.md + meta.json
        # 老版扁平路径:<doc_id>/raw.md + meta.json(向后兼容读取)
        if db_id:
            cache_path = cache_dir / db_id / doc_id / "raw.md"
            legacy_cache_path = cache_dir / doc_id / "raw.md"
        else:
            cache_path = cache_dir / doc_id / "raw.md"
            legacy_cache_path = None  # 没有更老的路径可回退

        # 优先检查新路径
        candidate = cache_path
        if not candidate.exists() and legacy_cache_path is not None and legacy_cache_path != cache_path:
            candidate = legacy_cache_path
        if candidate.exists():
            try:
                mtime = path.stat().st_mtime
                meta = candidate.with_name("meta.json")
                if meta.exists():
                    obj = json.loads(meta.read_text(encoding="utf-8"))
                    if obj.get("mtime") == mtime and obj.get("size") == size:
                        return {
                            "markdown": candidate.read_text(encoding="utf-8"),
                            "method": "cache",
                            "cache_hit": True,
                        }
            except Exception:
                pass  # fall through to re-parse

    if suffix in _MINERU_EXTS:
        data = path.read_bytes()
        result = _call_mineru(data, url=url)
        md = result.get("md")
        if not md:
            content = result.get("content") or []
            md = "\n".join(content) if isinstance(content, list) else str(content)
        if not md:
            raise RuntimeError("MinerU returned no markdown or content")
        method = "mineru"
    elif suffix in _PLAIN_EXTS:
        md = _read_plain(path)
        method = "plain"
    elif suffix in _PANDOC_EXTS:
        md = _read_pandoc(path)
        method = "pandoc"
    elif suffix in _PYTHON_OPENPYXL_EXTS:
        md = _read_xlsx(path)
        method = "openpyxl"
    else:
        # Unknown extension: best-effort plain text read
        md = _read_plain(path)
        method = "plain"

    if use_cache and cache_path is not None:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(md, encoding="utf-8")
            meta = cache_path.with_name("meta.json")
            meta.write_text(
                json.dumps({"mtime": path.stat().st_mtime, "size": size}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass  # cache write is best-effort

    return {"markdown": md, "method": method, "cache_hit": False}


# ---------------------------------------------------------------------------
# Type-aware dispatcher used by the upload pipeline
# ---------------------------------------------------------------------------

ParserFunc = Callable[[Path], str]


def default_parser_registry() -> Dict[str, ParserFunc]:
    """Return registry of {extension: parser_fn} for current environment."""
    reg: Dict[str, ParserFunc] = {}
    for ext in _PLAIN_EXTS:
        reg[ext] = _read_plain
    if shutil.which("pandoc"):
        for ext in _PANDOC_EXTS:
            reg[ext] = _read_pandoc
    try:
        import openpyxl  # type: ignore  # noqa: F401

        for ext in _PYTHON_OPENPYXL_EXTS:
            reg[ext] = _read_xlsx
    except ImportError:
        pass
    return reg
