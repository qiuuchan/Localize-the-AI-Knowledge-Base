"""v1.7.0 · safe-eject.ps1 跨平台对话框测试(5 测)

覆盖 plan §三 阶段 3c:safe-eject.ps1 弹"现在可以拔出"对话框
从 Windows Forms MessageBox 改为 Show-KBAINotice(平台分支)。
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SAFE_EJECT = REPO / "scripts" / "safe-eject.ps1"


def _read() -> str:
    return SAFE_EJECT.read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# 1) 必须 dot-source platform-utils
# ----------------------------------------------------------------------


def test_safe_eject_dot_sources_platform_utils():
    """safe-eject.ps1 必须 dot-source platform-utils(为 Show-KBAINotice)。"""
    content = _read()
    assert "lib/platform-utils.ps1" in content, \
        "safe-eject.ps1 未 dot-source platform-utils.ps1"


# ----------------------------------------------------------------------
# 2) MessageBox 替换为 Show-KBAINotice
# ----------------------------------------------------------------------


def test_no_direct_messagebox_call():
    """safe-eject.ps1 不应直接调 System.Windows.Forms.MessageBox::Show。

    原:v1.6.0 直接调 WinForms MessageBox(Mac 无 WinForms → 弹窗失败)
    新:v1.7.0 走 Show-KBAINotice(平台分支)
    """
    content = _read()
    assert "MessageBox]::Show" not in content, \
        "safe-eject.ps1 仍有直接 Windows Forms MessageBox 调用,应改 Show-KBAINotice"


def test_uses_show_kbai_notice():
    """safe-eject.ps1 弹窗必须用 Show-KBAINotice(平台感知)。"""
    content = _read()
    assert "Show-KBAINotice" in content, \
        "safe-eject.ps1 缺 Show-KBAINotice 调用"


# ----------------------------------------------------------------------
# 3) 平台分支文案(Win + Mac 步骤差异)
# ----------------------------------------------------------------------


def test_message_mentions_both_platforms():
    """安全拔出消息应同时提到 Windows + macOS 操作步骤(跨平台文档)。"""
    content = _read()
    # 消息体里同时含 Windows / macOS 指引
    assert "Windows" in content or "windows" in content, \
        "safe-eject.ps1 缺 Windows 操作指引"
    assert "macOS" in content, \
        "safe-eject.ps1 缺 macOS 操作指引(拖到废纸篓)"


# ----------------------------------------------------------------------
# 4) 解析检查
# ----------------------------------------------------------------------


def test_parses_clean():
    """safe-eject.ps1 必须通过 PowerShell 解析器检查(无语法错误)。"""
    import subprocess
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "$t=$null;$e=$null;"
         "[System.Management.Automation.Language.Parser]::ParseFile('" + str(SAFE_EJECT) + "',[ref]$t,[ref]$e)|Out-Null;"
         "if($e){$e|%%{$_.Message};exit 1}else{exit 0}"],
        capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, f"safe-eject.ps1 parse errors: {proc.stdout} {proc.stderr}"
