"""Shutdown / safe-eject endpoint."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.core.config import get_root_dir
from backend.core.ps_runner import run_ps

router = APIRouter()


@router.post("/shutdown")
def shutdown() -> dict:
    """Call safe-eject.ps1 in non-interactive mode and stop the services."""
    root = get_root_dir()
    result = run_ps(
        root / "scripts" / "safe-eject.ps1",
        args=["-AutoYes", "-NoMessageBox", "-ReturnExitCode"],
        cwd=root,
        timeout=120,
    )
    code = result["returncode"]
    # safe-eject returns 0 for clean stop, 2 if stop.bat had issues but eject advice is given
    if code not in (0, 2):
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "exit_code": code,
                "stderr": result["stderr"],
                "stdout": result["stdout"],
            },
        )
    return {
        "success": True,
        "exit_code": code,
        "message": "KB-AI 已停止，现在可以安全弹出 U 盘",
    }
