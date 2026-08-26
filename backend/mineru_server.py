"""
MinerU-compatible local HTTP API for KB-AI parse-doc.ps1.
Backed by modern MinerU 3.x CLI (`mineru -p <path> -o <dir> ...`).
Exposes legacy /health and /file_parse endpoints expected by scripts/parse-doc.ps1.
"""
import base64
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import JSONResponse

app = FastAPI(title="KB-AI MinerU-compatible API", version="0.3.0")


class ParseRequest(BaseModel):
    file: str
    backend: str = "pipeline"
    parse_method: str = "auto"
    language: str = "ch"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/file_parse")
def file_parse(req: ParseRequest):
    tmp_dir = tempfile.mkdtemp(prefix="mineru_")
    try:
        data = base64.b64decode(req.file)
        ext = _guess_ext(data)
        # Sanitize filename: parse-doc.ps1 may send a generic name; keep extension only
        input_path = Path(tmp_dir) / f"input{ext}"
        input_path.write_bytes(data)

        if ext not in (".pdf", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg"):
            return JSONResponse(status_code=400, content={"error": f"unsupported extension {ext}"})

        md = _parse_with_mineru(input_path, tmp_dir, req.method if hasattr(req, "method") else req.parse_method, req.language)
        return {"md": md}
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _guess_ext(data: bytes) -> str:
    if data[:4] == b"%PDF":
        return ".pdf"
    if data[:4] == b"PK\x03\x04":
        return ".pptx"
    # docx and xlsx also start with PK\x03\x04; we rely on parse-doc.ps1 sending the correct file type
    return ".pdf"


def _parse_with_mineru(input_path: Path, tmp_dir: str, method: str, language: str) -> str:
    """Run MinerU CLI and read generated markdown."""
    out_dir = Path(tmp_dir) / "out"
    out_dir.mkdir()

    method = method if method in ("auto", "txt", "ocr") else "auto"

    # Use the MinerU CLI entry point executable installed in the same venv.
    if sys.platform == "win32":
        mineru_exe = Path(sys.executable).parent / "mineru.exe"
    else:
        mineru_exe = Path(sys.executable).parent / "mineru"
    cmd = [
        str(mineru_exe),
        "-p", str(input_path),
        "-o", str(out_dir),
        "-m", method,
        "-b", "pipeline",
        "-l", language,
    ]

    env = os.environ.copy()
    env.setdefault("MINERU_MODEL_SOURCE", "huggingface")
    # Large PDFs (50+ pages) need more than the default 300s to render images on CPU.
    env.setdefault("MINERU_PDF_RENDER_TIMEOUT", "1800")
    # v1.5.1: 移除硬编码代理 127.0.0.1:7897(开发机代理)。
    # 客户环境无该代理,会触发 urllib 拒绝连接。改为"如客户系统有代理,自设 HTTP_PROXY/HTTPS_PROXY"。
    # U 盘已预置 models/huggingface/,start.bat 复制到 %USERPROFILE%\.cache\,
    # 正常情况下不会触发首次下载,无需代理。

    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=1800)
    if result.returncode != 0:
        raise RuntimeError(f"mineru CLI failed ({result.returncode}):\n{result.stderr}\n{result.stdout}")

    # MinerU writes: <out_dir>/<stem>/<method>/<stem>.md
    md_files = list(out_dir.rglob("*.md"))
    if not md_files:
        raise RuntimeError("mineru produced no markdown file")

    # Return the deepest/directory markdown (most specific)
    md_files.sort(key=lambda p: len(p.parts), reverse=True)
    return md_files[0].read_text(encoding="utf-8", errors="ignore")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
