"""Tests for v1.5.1 ps_runner graceful degradation.

When the host PowerShell script does not exist (container environment),
run_ps() must return a "skipped" result instead of raising.
"""
from __future__ import annotations

from backend.core.ps_runner import run_ps


def test_run_ps_missing_script_returns_skipped(tmp_path):
    """run_ps returns skipped=True when script path does not exist."""
    nonexistent = tmp_path / "does_not_exist.ps1"
    result = run_ps(nonexistent)
    assert result["skipped"] is True
    assert result["returncode"] == 0  # not a failure
    assert result["json"] is None
    assert "script not found" in result["stderr"]


def test_run_ps_missing_script_no_powershell_invoked(tmp_path, monkeypatch):
    """run_ps must NOT invoke pwsh when script is missing."""
    nonexistent = tmp_path / "nope.ps1"
    pwsh_calls = []

    def fake_popen(*args, **kwargs):
        pwsh_calls.append(args)
        raise AssertionError("pwsh should not be invoked for missing script")

    monkeypatch.setattr("subprocess.run", fake_popen)
    result = run_ps(nonexistent)
    assert pwsh_calls == [], "pwsh must not be called for missing script"
    assert result["skipped"] is True


def test_run_ps_existing_script_does_not_return_skipped(tmp_path):
    """run_ps on existing script should not set skipped=True."""
    import shutil

    real_script = tmp_path / "trivial.ps1"
    real_script.write_text('Write-Output "{}"', encoding="utf-8")

    # Skip if pwsh not installed in test env (CI / dev box may not have it)
    if not shutil.which("pwsh") and not shutil.which("powershell"):
        import pytest

        pytest.skip("pwsh/powershell not installed in test env")

    result = run_ps(real_script, args=["-NoProfile"])
    assert result.get("skipped") is not True, (
        "real script must not return skipped=True even if pwsh exits non-zero"
    )


def test_run_ps_returncode_zero_on_skip(tmp_path):
    """Skipped result has returncode=0 so callers don't treat as error."""
    result = run_ps(tmp_path / "missing.ps1")
    assert result["returncode"] == 0
    # Caller can detect skip via "skipped" key, not via returncode


def test_run_ps_skipped_includes_path_in_stderr(tmp_path):
    """Skipped result stderr mentions the path that was missing (debug aid)."""
    missing = tmp_path / "i_do_not_exist.ps1"
    result = run_ps(missing)
    assert str(missing) in result["stderr"]


def test_run_ps_skipped_returns_empty_stdout(tmp_path):
    """Skipped result stdout is empty (no spurious content)."""
    result = run_ps(tmp_path / "absent.ps1")
    assert result["stdout"] == ""
    assert result["json"] is None