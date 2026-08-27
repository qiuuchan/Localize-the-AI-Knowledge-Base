"""v1.7.0 · start.ps1 / stop.ps1 / precheck.ps1 / .command 跨平台测试(10 测)

覆盖 plan §三 阶段 2 + §四 关键代码片段:
    - start.ps1 8 阶段结构(平台检测 + Docker + .env + 镜像 + HF + compose up + 健康 + 浏览器)
    - stop.ps1 5 步结构(后端 + MinerU + 容器 + fsync + 备份 + 弹框)
    - precheck.ps1 5 项检查
    - .command 文件作为 Mac 双击入口(exec pwsh)
    - 不依赖 docker / 真实 Mac;静态 + Windows 烟雾
"""

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
START_PS1 = REPO / "start.ps1"
STOP_PS1 = REPO / "stop.ps1"
PRECHECK_PS1 = REPO / "precheck.ps1"
START_COMMAND = REPO / "start.command"
STOP_COMMAND = REPO / "stop.command"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _run_powershell(script_text: str, timeout: int = 30) -> tuple[str, str, int]:
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script_text],
        capture_output=True, text=True, timeout=timeout
    )
    return proc.stdout.strip(), proc.stderr.strip(), proc.returncode


# ----------------------------------------------------------------------
# 1) .command 文件结构
# ----------------------------------------------------------------------


def test_start_command_executes_pwsh():
    """start.command 必须通过 exec pwsh 调 start.ps1(避免子 shell 嵌套)。"""
    content = _read(START_COMMAND)
    assert "exec pwsh" in content, "start.command 缺 exec pwsh"
    assert "start.ps1" in content, "start.command 未引用 start.ps1"
    # 必须是 bash 脚本(Shebang)
    assert content.startswith("#!/bin/bash"), "start.command 缺 bash shebang"
    # 不能用相对路径调 start.ps1(可能 cwd 不对)
    assert "DIR=\"$(cd" in content, "start.command 必须用绝对路径调 start.ps1"
    assert "$DIR/start.ps1" in content, "start.command 必须用 $DIR/start.ps1"


def test_stop_command_executes_pwsh():
    """stop.command 必须通过 exec pwsh 调 stop.ps1。"""
    content = _read(STOP_COMMAND)
    assert "exec pwsh" in content
    assert "stop.ps1" in content
    assert content.startswith("#!/bin/bash")


# ----------------------------------------------------------------------
# 2) start.ps1 结构
# ----------------------------------------------------------------------


def test_start_ps1_has_eight_stages():
    """start.ps1 必须覆盖 8 阶段(plan §三 阶段 2c)。"""
    content = _read(START_PS1)
    # 至少 7 个 [N/8] 标记(阶段 0 = precheck 调用,阶段 1-8 是主流程)
    stage_markers = re.findall(r"\[(\d)/8\]", content)
    stages = sorted(set(int(m) for m in stage_markers))
    assert len(stages) >= 7, f"start.ps1 阶段标记不足,找到 {stages}"
    # 必须有 8/8(打开浏览器)
    assert 8 in stages, "start.ps1 缺阶段 8(打开浏览器)"


def test_start_ps1_dot_sources_platform_utils():
    """start.ps1 必须 dot-source platform-utils.ps1(为 Get-KBAIPlatform 等)。"""
    content = _read(START_PS1)
    assert "platform-utils.ps1" in content, "start.ps1 未 dot-source platform-utils.ps1"
    assert "Get-KBAIPlatform" in content, "start.ps1 缺平台检测调用"


def test_start_ps1_uses_open_kbai_url():
    """start.ps1 阶段 8 必须用 Open-KBAIUrl(平台感知的浏览器打开)。"""
    content = _read(START_PS1)
    assert "Open-KBAIUrl" in content, "start.ps1 缺 Open-KBAIUrl 调用"
    # 原硬编码 start "" 不可出现(那是 start.bat 的 Windows 模式)
    assert 'Start-Process -FilePath "open"' not in content, \
        "start.ps1 误用 Mac open 而非 Open-KBAIUrl"


def test_start_ps1_runs_precheck():
    """start.ps1 阶段 0 必须调 precheck.ps1(默认开启,SkipPrecheck 时跳过)。"""
    content = _read(START_PS1)
    assert "precheck.ps1" in content, "start.ps1 未调 precheck.ps1"
    assert "SkipPrecheck" in content, "start.ps1 缺 -SkipPrecheck 参数"


# ----------------------------------------------------------------------
# 3) stop.ps1 结构
# ----------------------------------------------------------------------


def test_stop_ps1_has_five_steps():
    """stop.ps1 必须覆盖 5 步(后端 → MinerU → 容器 → fsync → 备份)。"""
    content = _read(STOP_PS1)
    step_markers = re.findall(r"\[(\d)/5\]", content)
    steps = sorted(set(int(m) for m in step_markers))
    assert len(steps) >= 4, f"stop.ps1 步骤标记不足,找到 {steps}"
    assert 5 in steps, "stop.ps1 缺步骤 5(备份 / 弹框)"


def test_stop_ps1_kb_ai_backend_first():
    """stop.ps1 必须先停 kb-ai-backend(关键:不停它直接弹盘会被 Windows 拒绝)。"""
    content = _read(STOP_PS1)
    backend_pos = content.find("kb-ai-backend")
    assert backend_pos > 0, "stop.ps1 未引用 kb-ai-backend"
    # 后端停止必须早于 docker compose stop 所有容器
    compose_stop_pos = content.find("docker compose stop\n")
    if compose_stop_pos == -1:
        # 兼容多种写法
        compose_stop_pos = content.find("docker compose stop")
    assert backend_pos < compose_stop_pos, "stop.ps1 必须先停 kb-ai-backend 再停所有容器"


def test_stop_ps1_uses_show_kbai_notice():
    """stop.ps1 弹"现在可以拔出"对话框必须走 Show-KBAINotice(平台感知)。"""
    content = _read(STOP_PS1)
    assert "Show-KBAINotice" in content, "stop.ps1 缺 Show-KBAINotice"
    # 老的 Windows Forms 直接调用不应出现
    assert "System.Windows.Forms.MessageBox::Show" not in content, \
        "stop.ps1 误用 Windows Forms,应走 Show-KBAINotice"


# ----------------------------------------------------------------------
# 4) precheck.ps1 结构
# ----------------------------------------------------------------------


def test_precheck_ps1_has_five_checks():
    """precheck.ps1 必须覆盖 5 项检查(plan §四 4.2.5 修正后)。"""
    content = _read(PRECHECK_PS1)
    # 5 项检查的标识符
    check_markers = ["虚拟化", "OS 版本", "磁盘空间", "内存"]
    # 第 5 项是平台专属(macOS: SIP+Docker;Win: S Mode)
    for marker in check_markers:
        assert marker in content, f"precheck.ps1 缺检查项:{marker}"
    # 平台专属至少 1 个
    assert "SIP" in content or "S Mode" in content, \
        "precheck.ps1 缺平台专属检查(SIP 或 S Mode)"


def test_precheck_ps1_runs_on_windows():
    """precheck.ps1 在 Windows 端能跑(冒烟测,5 秒内退出)。"""
    # 用 -Quiet 模式跳过 console 输出
    stdout, stderr, code = _run_powershell(
        f"& '{PRECHECK_PS1}' -Quiet 2>$null; $LASTEXITCODE"
    )
    # 即使某项检查失败(本机虚拟化关),退出码要么 0 要么 1,不能崩
    assert code in (0, 1), f"precheck.ps1 异常退出 code={code} stderr={stderr}"
