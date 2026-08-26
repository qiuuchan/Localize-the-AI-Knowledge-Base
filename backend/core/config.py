"""KB-AI backend configuration and project root discovery."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

# Placeholder values copied from scripts/lib/load-env.ps1
_PLACEHOLDER_PATTERNS = [
    "PLEASE-FILL-IN",
    "sk-PLEASE-FILL-IN",
    "sk-PLEASE-FILL-IN-YOUR-ALIYUN-BAILIAN-API-KEY",
    "tvly-PLEASE-FILL-IN",
    "changeme",
]


def _is_placeholder(value: str) -> bool:
    value = value.strip()
    if not value:
        return True
    for p in _PLACEHOLDER_PATTERNS:
        if value == p or value.lower().startswith(p.lower()):
            return True
    return False


def get_root_dir() -> Path:
    """Return project root.

    Priority:
      1. KB_AI_ROOT environment variable
      2. Parent directory of backend/ (this file is at backend/core/config.py)
    """
    env_root = os.environ.get("KB_AI_ROOT", "").strip()
    if env_root:
        p = Path(env_root)
        if p.exists():
            return p
    # backend/core/config.py -> backend -> project root
    return Path(__file__).resolve().parent.parent.parent


def get_env_path() -> Path:
    return get_root_dir() / ".env"


def get_env_var(name: str, env_path: Optional[Path] = None) -> Optional[str]:
    """Read a variable from the .env file, mirroring scripts/lib/load-env.ps1.

    - Skips blank/comment lines.
    - KEY=value, value can contain '='.
    - Strips inline comments matching r'^(.*?)\\s+#\\s'.
    - Treats placeholder values as None.
    """
    if env_path is None:
        env_path = get_env_path()
    if not env_path.exists():
        return None
    try:
        text = env_path.read_text(encoding="utf-8")
    except Exception:
        return None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        eq = line.find("=")
        if eq == -1:
            continue
        key = line[:eq].strip()
        if key != name:
            continue
        value = line[eq + 1 :].strip()
        # strip inline comment only when # is preceded by whitespace
        m = re.search(r"^(.*?)\s+#\s", value)
        if m:
            value = m.group(1).strip()
        if _is_placeholder(value):
            return None
        return value
    return None


def get_data_dir() -> Path:
    return get_root_dir() / "data"


def get_db_path() -> Path:
    # Aligned with chat.ps1 (v0.7.2): sessions/messages live in db.sqlite
    return get_data_dir() / "db.sqlite"


def get_env_or_env_var(name: str) -> Optional[str]:
    """Env variable wins over .env file, mirroring Resolve-ApiKey priority."""
    env_val = os.environ.get(name, "").strip()
    if env_val and not _is_placeholder(env_val):
        return env_val
    return get_env_var(name)
