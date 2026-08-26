"""v1.7.0 · platform-utils.ps1 跨平台工具测试(12 测)

不依赖 docker / 真实 Mac;既做静态合规(PS 5.1 兼容、函数完整、$script: 污染),
也做 Windows 端功能性烟雾测试(实际跑 PowerShell 检查返回值)。

设计原则:
    1. 静态测试覆盖 plan §十 修正记录中的合规要求(无 $IsMacOS、9 个函数齐全、heredoc 而非 -e)
    2. 功能测试在 Windows 端跑通(同代码在 macOS 端通过 pwsh 跑等价)
    3. 不依赖 pytest 之外的工具(纯 stdlib + subprocess)
"""

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PLATFORM_UTILS = REPO / "scripts" / "lib" / "platform-utils.ps1"
START_BACKEND = REPO / "scripts" / "start-backend.ps1"
RUN_CHECKS = REPO / "scripts" / "run-checks.ps1"
PRE_COMMIT = REPO / "scripts" / "hooks" / "pre-commit"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# 1) 文件存在 + 编码 + 大小
# ----------------------------------------------------------------------


def test_file_exists_at_lib():
    """platform-utils.ps1 必须在 scripts/lib/ 下(沿用 lib/ 共享助手约定)。"""
    assert PLATFORM_UTILS.exists(), f"missing: {PLATFORM_UTILS}"
    assert PLATFORM_UTILS.parent.name == "lib"


def test_utf8_no_bom():
    """UTF-8 无 BOM(沿用项目所有 .ps1 文件约定,见 AGENTS.md §3 #2)。"""
    raw = PLATFORM_UTILS.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "platform-utils.ps1 含 UTF-8 BOM"
    # 应当是合法 UTF-8
    raw.decode("utf-8")


# ----------------------------------------------------------------------
# 2) PS 5.1 兼容(关键红线,AGENTS.md §3.1)
# ----------------------------------------------------------------------


def test_no_dollar_is_mac_os_automatic_variable():
    """禁止使用 $IsMacOS / $IsLinux / $IsWindows(PS 6+ 自动变量,PS 5.1 上是 $null)。

    这是 plan §十-1 修正的核心点;若发现即视为违反 AGENTS.md §3.1 红线。
    允许在注释 / 文档中提及(负向断言:行首不是 # 且不在文档块内)。
    """
    content = _read(PLATFORM_UTILS)
    # 只检测实际代码(去除注释行 / <# ... #> 文档块)
    code_lines = []
    in_doc_block = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("<#"):
            in_doc_block = True
            continue
        if in_doc_block:
            if stripped.endswith("#>"):
                in_doc_block = False
            continue
        if stripped.startswith("#"):
            continue
        code_lines.append(line)
    code = "\n".join(code_lines)

    # 检测 $IsMacOS / $IsLinux / $IsWindows 单独出现(不是 $env: 等前缀)
    for var in ("$IsMacOS", "$IsLinux", "$IsWindows"):
        # 必须作为 token 出现(避免误伤 $IsMacOSStr 这种自定变量)
        pattern = re.compile(rf"\{var}\b")
        matches = pattern.findall(code)
        assert not matches, f"platform-utils.ps1 代码中含 PS 6+ 自动变量 {var}:{matches}"


# ----------------------------------------------------------------------
# 3) 函数完整性(11 个函数,见 plan §四 4.1)
# ----------------------------------------------------------------------


EXPECTED_FUNCTIONS = [
    "Get-KBAIPlatform",
    "Get-KBAIPythonVenvPath",
    "Get-KBAIPythonVenvPip",
    "Get-KBAIPythonVenvUvicorn",
    "Open-KBAIUrl",
    "Show-KBAINotice",
    "Get-KBAICpuVirtualization",
    "Get-KBAIOSVersion",
    "Get-KBAIDiskFreeGB",
    "Get-KBAIMemoryGB",
    "Test-KBAISIPStatus",
]


def test_all_eleven_functions_defined():
    """11 个工具函数必须全部存在(plan §四 4.1)。"""
    content = _read(PLATFORM_UTILS)
    missing = [f for f in EXPECTED_FUNCTIONS if f"function {f}" not in content]
    assert not missing, f"missing functions: {missing}"


# ----------------------------------------------------------------------
# 4) 函数而非 $script: 变量(避免 dot-source 作用域污染)
# ----------------------------------------------------------------------


def test_no_script_scope_platform_variable():
    """禁止用 $script:KBAIPlatform 模块级变量(plan §十-2 修正)。

    dot-source 把 platform-utils 的代码 inline 到 caller,$script: 指向 caller
    script 而非 platform-utils 自身,会导致多脚本 dot-source 时变量互相污染。
    正确做法:用 Get-KBAIPlatform 函数,每次调用重新检测。
    """
    content = _read(PLATFORM_UTILS)
    assert "$script:KBAIPlatform" not in content, \
        "platform-utils.ps1 用 $script:KBAIPlatform 会污染 dot-source caller"


# ----------------------------------------------------------------------
# 5) Show-KBAINotice 必须用 heredoc + stdin(plan §十-3)
# ----------------------------------------------------------------------


def test_show_kbai_notice_uses_stdin_heredoc():
    """Show-KBAINotice 的 macOS 分支必须用 stdin + heredoc,不能用 osascript -e。

    osascript -e 字符串参数对中文/换行/单引号 escape 极脆弱,导致 safe-eject 在
    Mac 中文客户场景乱码。heredoc 走 stdin 是 AppleScript 官方推荐做法。
    """
    content = _read(PLATFORM_UTILS)
    # 找 Show-KBAINotice 函数体
    m = re.search(r"function Show-KBAINotice\s*\{(.*?)\n\}", content, re.DOTALL)
    assert m, "Show-KBAINotice 函数未找到"
    body = m.group(1)
    # macOS 分支应该用 | & osascript(管道喂 stdin)
    assert "| & osascript" in body, \
        "Show-KBAINotice macOS 分支未用 stdin 喂 osascript"
    # 显式 -l AppleScript 标识语言
    assert "-l AppleScript" in body, \
        "Show-KBAINotice 应显式指定 -l AppleScript"


# ----------------------------------------------------------------------
# 6) 调用方已迁移到 platform-utils(3 处修复全部到位)
# ----------------------------------------------------------------------


def test_start_backend_uses_platform_utils():
    """scripts/start-backend.ps1 必须 dot-source platform-utils 并用 3 个 Get 函数。

    原:行 38, 39, 85 硬编码 .venv/Scripts/{python,pip,uvicorn}.exe
    新:走 Get-KBAIPythonVenvPath / Pip / Uvicorn 自动平台切换
    """
    content = _read(START_BACKEND)
    assert "lib/platform-utils.ps1" in content, \
        "start-backend.ps1 未 dot-source platform-utils.ps1"
    assert "Get-KBAIPythonVenvPath" in content
    assert "Get-KBAIPythonVenvPip" in content
    assert "Get-KBAIPythonVenvUvicorn" in content
    # 原硬编码路径必须全部移除
    assert '.venv/Scripts/python.exe' not in content
    assert '.venv/Scripts/pip.exe' not in content
    assert '.venv/Scripts/uvicorn.exe' not in content


def test_run_checks_uses_platform_utils():
    """scripts/run-checks.ps1 必须 dot-source platform-utils 并用 Get 函数。"""
    content = _read(RUN_CHECKS)
    assert "lib/platform-utils.ps1" in content, \
        "run-checks.ps1 未 dot-source platform-utils.ps1"
    assert "Get-KBAIPythonVenvPath" in content
    # 原硬编码路径必须移除
    assert 'backend\\.venv\\Scripts\\python.exe' not in content


def test_pre_commit_has_mac_ruff_fallback():
    """scripts/hooks/pre-commit 必须有 .venv/bin/ruff 的 Mac/Linux 分支。

    原:只有 backend/.venv/Scripts/ruff.exe(Windows-only)
    新:加 elif backend/.venv/bin/ruff(Mac/Linux 通用)
    """
    content = _read(PRE_COMMIT)
    assert "backend/.venv/bin/ruff" in content, \
        "pre-commit 缺 Mac/Linux venv bin/ruff 分支"
    assert "elif [ -x" in content, \
        "pre-commit 缺 elif 平台分支"


# ----------------------------------------------------------------------
# 7) dot-source 守卫
# ----------------------------------------------------------------------


def test_dot_source_guard_present():
    """platform-utils.ps1 必须有 dot-source 守卫,被 dot-source 时只暴露函数不执行主流程。

    沿用 lib/ 共享助手约定(见 lib/load-env.ps1:204-206)。
    """
    content = _read(PLATFORM_UTILS)
    assert "$MyInvocation.InvocationName -eq '.'" in content, \
        "platform-utils.ps1 缺 dot-source 守卫"
    # 必须有 'return'(在守卫分支内)
    assert re.search(r"if\s*\(\s*\$MyInvocation\.InvocationName\s*-eq\s*'\.'\s*\)\s*\{[^}]*return", content, re.DOTALL), \
        "dot-source 守卫缺 return"


# ----------------------------------------------------------------------
# 8) Windows 端功能烟雾测试(实际跑 PowerShell)
# ----------------------------------------------------------------------


def _run_powershell(script_text: str) -> tuple[str, str, int]:
    """用 powershell 跑一段 PS 代码,返回 (stdout, stderr, exitcode)。"""
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script_text],
        capture_output=True, text=True, timeout=30
    )
    return proc.stdout.strip(), proc.stderr.strip(), proc.returncode


def test_get_kbai_platform_returns_windows():
    """在 Windows 端跑 Get-KBAIPlatform 必须返回 'Windows'。"""
    stdout, stderr, code = _run_powershell(
        f". '{PLATFORM_UTILS}'; Get-KBAIPlatform"
    )
    assert code == 0, f"powershell exit={code} stderr={stderr}"
    assert stdout == "Windows", f"expected 'Windows', got '{stdout}'"


def test_get_kbai_python_venv_path_windows():
    """Windows 端 Get-KBAIPythonVenvPath 必须返回 .venv/Scripts/python.exe。"""
    stdout, _, _ = _run_powershell(
        f". '{PLATFORM_UTILS}'; "
        f"Get-KBAIPythonVenvPath -BackendDir 'E:/backend'"
    )
    assert "Scripts" in stdout
    assert "python.exe" in stdout
    # 不应走 bin/(Windows 上 scripts/ 是约定)
    assert "bin/python" not in stdout
