"""Run PowerShell scripts and decode their UTF-8 output."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, List, Optional


def _find_powershell() -> str:
    """Prefer pwsh (7+), fall back to Windows PowerShell 5.1."""
    for cmd in ("pwsh", "powershell"):
        if shutil.which(cmd):
            return cmd
    raise RuntimeError("PowerShell (pwsh/powershell) not found on PATH")


def run_ps(
    script_path: Path,
    args: Optional[List[str]] = None,
    cwd: Optional[Path] = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """Run a PowerShell script with -ExecutionPolicy Bypass and return parsed output.

    Returns a dict with:
      - stdout: decoded stdout string
      - stderr: decoded stderr string
      - returncode: process exit code
      - json: parsed JSON if stdout contains JSON, else None
      - skipped: True if script_path does not exist (v1.5.1:容器无 host PS 脚本时 graceful return)
    """
    # v1.5.1:容器环境无 host PS 脚本时优雅降级,避免 /api/health 503
    if not Path(script_path).exists():
        return {
            "stdout": "",
            "stderr": f"script not found: {script_path}",
            "returncode": 0,  # 不算失败
            "json": None,
            "skipped": True,
        }
    ps = _find_powershell()
    cmd: List[str] = [
        ps,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
    ]
    if args:
        cmd.extend(args)

    workdir = cwd or script_path.parent
    proc = subprocess.run(
        cmd,
        cwd=str(workdir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )

    stdout = proc.stdout.decode("utf-8", errors="replace").strip()
    stderr = proc.stderr.decode("utf-8", errors="replace").strip()

    parsed: Any = None
    if stdout:
        # Scripts that emit -OutputJson usually mix Write-Host with the JSON.
        # Find the first JSON object '{' at the start of a line.
        m = re.search(r"(?m)^\s*\{", stdout)
        if m:
            try:
                parsed = json.loads(stdout[m.start() :])
            except Exception:
                parsed = None

    return {
        "stdout": stdout,
        "stderr": stderr,
        "returncode": proc.returncode,
        "json": parsed,
    }


def run_ps_raise(
    script_path: Path,
    args: Optional[List[str]] = None,
    cwd: Optional[Path] = None,
    timeout: int = 300,
) -> Any:
    """Like run_ps, but raise RuntimeError on non-zero exit code."""
    result = run_ps(script_path, args=args, cwd=cwd, timeout=timeout)
    if result["returncode"] != 0:
        detail = result["stderr"] or result["stdout"]
        raise RuntimeError(
            f"PowerShell script failed (exit={result['returncode']}): {detail[:500]}"
        )
    return result
