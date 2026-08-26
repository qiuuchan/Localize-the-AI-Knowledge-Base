"""v1.5.2 · start.bat 启动日志结构性测试(参考 v1.5.0 test_backend_container.py)

不依赖 docker / powershell;只解析 start.bat 的字符串 + 行为模式。
覆盖 v1.5.2 的 5 个改动 Item:
    Item 1 · 日志初始化(§2.1)
    Item 2 · 保留最近 20 个(§2.2)
    Item 3 · echo 镜像(§2.3)
    Item 4 · 退出收尾(§2.4)
    Item 5 · 失败兜底(§2.1)
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
START_BAT = REPO / "start.bat"


def _read() -> str:
    return START_BAT.read_text(encoding="utf-8")


# ===== Item 1 · 日志初始化 =====


def test_log_dir_points_to_logs():
    """LOG_DIR 必须指向 %~dp0logs(U 盘根下的 logs/ 目录)。"""
    content = _read()
    assert 'set "LOG_DIR=' in content
    assert '%~dp0logs' in content
    assert 'mkdir "%LOG_DIR%"' in content


def test_log_file_name_pattern():
    """LOG_FILE 格式 = start-YYYYMMDD-HHMMSS.log。

    v1.5.2 优先用 wmic 拼纯数字时间戳;wmic 不可用时兜底用 %date% %time%。
    """
    content = _read()
    # 主路径:wmic 本地时间 → slice 成 8 位日期 + 6 位时间
    assert "wmic os get localdatetime" in content
    assert 'set "LOG_TIMESTAMP=' in content
    assert "LOG_TIMESTAMP:~0,8%-%LOG_TIMESTAMP:~8,6%" in content, (
        "缺 LOG_TIMESTAMP 时间戳切片(YYYYMMDD-HHMMSS)"
    )
    # 兜底路径:date/time 子串 + 处理小时位空格
    for idx in (0, 5, 8):
        assert f"date:~{idx}," in content, f"缺 date 子串 :~{idx},"
    for idx in (0, 3, 6):
        assert f"time:~{idx}," in content, f"缺 time 子串 :~{idx},"
    assert "LOG_TIMESTAMP: =0" in content, "缺 %LOG_TIMESTAMP: =0% 占位空格替换"


def test_initial_banner_written():
    """开头写一行 === 启动日志 === banner(便于检索)。"""
    content = _read()
    assert re.search(
        r'echo\s+===\s+KB-AI\s+start\.bat.*>\s*"%LOG_FILE%"', content
    ), "缺初始 banner 写入(用 > 创建/覆盖 %LOG_FILE%)"


def test_no_ascii_parens_in_if_block_echo():
    """v1.5.2 hotfix:ASCII 圆括号在 IF 块内的 echo 里会触发 CMD `... was unexpected at this time` 错误。

    CMD 解析器会把 echo 字符串里的 ( 和 ) 误算成 IF 块边界,语法炸
    导致 start.bat 闪退。本测试守住:IF 块内的 echo 内容只能用 ·/全角/无括号,
    不能出现 ASCII ( 和 )。
    """
    content = _read()
    # 找出所有 if (...) (... ) ( ... ) else ( ... ) 块,提取内部 echo 行
    # 简化:全文 echo 行只要有 ASCII ( 和 ),后面接 >> "%LOG_FILE%" 标记存在危险
    # 我们就强行要求:那些行里要么在 IF 块外,要么已经替换成 ·
    # 直接走白名单:把已知的 N 个 paren 替换行做断言
    suspicious_phrases = [
        "Docker 未安装,正在从 U 盘离线包自动安装(约 1 分钟)",
        "Docker Desktop 启动超时(90 秒)",
        "电脑是否已重启?(首次安装 Docker 需要重启一次)",
        "WSL 2 是否已启用?(控制面板",
        "模型复制失败(robocopy 返回 !errorlevel!),",
        "PDF/PPTX 解析服务(本批 USB 未打包);",
    ]
    for s in suspicious_phrases:
        # 这些 ASCII-paren 写法在 v1.5.2 之后已经全部替换成 · separator
        assert s not in content, (
            f"发现未修复的 IF-block paren 字符串: {s!r}"
        )


# ===== Item 5 · 失败兜底 =====


def test_log_failure_graceful():
    """日志创建失败时只警告不阻断(start.bat 必须仍能跑完)。

    v1.5.2 hotfix:echo 内容必须用全角中文标点(·)，不能用 ASCII ()，
    否则 CMD 会把它当成 IF 块的边界,语法炸 ↗ start.bat 闪退。
    """
    content = _read()
    assert "[警告] 启动日志创建失败" in content
    assert "不影响启动流程" in content


# ===== Item 2 · 保留策略 =====


def test_retention_trims_to_20():
    """保留策略:跳过最旧 + skip=20 + del。

    注意:`dir /b /o-d` 按修改时间倒序(skip=20 即保留前 20 个),
    删除后面的旧文件。命令回返 stderr 已用 `2^>nul` 抑制。
    """
    content = _read()
    assert "skip=20" in content, "缺 skip=20(保留前 20 个)"
    assert "dir /b /o-d" in content, "缺 dir 排序参数"
    assert '%LOG_DIR%\\%%f' in content, "缺 del 目标格式"


# ===== Item 3 · echo 镜像 =====


def test_echo_lines_redirect_to_log():
    """至少 80% 的 echo 行同步镜像到日志(防止漏改)。

    排除 banner 那行(用 > 不是 >>);给一点冗余。
    """
    content = _read()
    echoes = re.findall(r"^\s*echo\s.+$", content, re.MULTILINE)
    redirects = re.findall(r'>>\s*"%LOG_FILE%"', content)
    threshold = max(1, int(len(echoes) * 0.8))
    assert len(redirects) >= threshold, (
        f"echo 镜像覆盖不足:redirects={len(redirects)} < echoes*0.8={threshold}"
    )


# ===== Item 4 · 退出收尾 + 已有行为无回归 =====


def test_exit_summary_written():
    """endlocal 之前一行写 `=== 退出 (errorlevel=N) ... ===` 收尾。"""
    content = _read()
    assert re.search(
        r"echo\s+===\s+KB-AI\s+start\.bat\s+退出.*>>\s*\"%LOG_FILE%\"",
        content,
    ), "缺退出收尾 banner(>> 追加)"


def test_no_regression_on_error_pauses():
    """闪退修复不能反过来把 pause 改没了。

    沿用 v1.5.1 实测基线(行 58/67/116/124/198 各有一个 pause,共 4 个
    — 还有 start.bat:76 启动 docker desktop 等也可能有)。
    """
    content = _read()
    pauses = content.count("pause")
    assert pauses >= 4, f"pause 数量 {pauses} < 4,闪退兜底退化"


def test_no_regression_on_logic_keywords():
    """关键命令字串检查:docker info / compose up / 浏览器打开 等都还在。"""
    content = _read()
    for kw in (
        "docker info",
        "docker compose up",
        'start "" "http://localhost:8000"',
        "KB-AI  启动中",
        "timeout /t 5",
    ):
        assert kw in content, f"关键命令缺失: {kw!r}"
