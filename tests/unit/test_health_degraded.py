"""Tests for v1.5.1 /api/health degraded path in container environment.

When the host PowerShell health-probe.ps1 is not available (container),
the endpoint must return 200 with status=degraded, NOT raise 503.
"""
from __future__ import annotations

from unittest.mock import patch


def test_health_returns_degraded_when_script_missing():
    """/api/health returns 200 + degraded JSON when ps script is missing."""
    from backend.api.health import get_health, _health_cache

    # Reset cache
    _health_cache["data"] = None
    _health_cache["at"] = 0.0

    # Mock run_ps to simulate "script not found"
    fake_skipped = {
        "stdout": "",
        "stderr": "script not found: /data/scripts/health-probe.ps1",
        "returncode": 0,
        "json": None,
        "skipped": True,
    }

    with patch("backend.api.health.run_ps", return_value=fake_skipped) as mock_ps:
        result = get_health()

    assert result["status"] == "degraded"
    assert result["mode"] == "container"
    assert "container" in result["note"].lower() or "skipped" in result["note"].lower()
    assert "timestamp" in result
    mock_ps.assert_called_once()


def test_health_does_not_raise_503_on_skipped():
    """Verify /api/health returns dict (not HTTPException) when skipped."""
    from backend.api.health import get_health, _health_cache

    _health_cache["data"] = None
    _health_cache["at"] = 0.0

    fake_skipped = {
        "stdout": "",
        "stderr": "script not found",
        "returncode": 0,
        "json": None,
        "skipped": True,
    }

    with patch("backend.api.health.run_ps", return_value=fake_skipped):
        # Must not raise HTTPException
        result = get_health()

    assert isinstance(result, dict)
    assert result["status"] == "degraded"


def test_health_includes_timestamp_iso():
    """Degraded response includes UTC timestamp."""
    from backend.api.health import get_health, _health_cache

    _health_cache["data"] = None
    _health_cache["at"] = 0.0

    fake_skipped = {
        "stdout": "",
        "stderr": "script not found",
        "returncode": 0,
        "json": None,
        "skipped": True,
    }

    with patch("backend.api.health.run_ps", return_value=fake_skipped):
        result = get_health()

    ts = result.get("timestamp", "")
    # ISO 8601 UTC has 'T' separator and '+00:00' or 'Z'
    assert "T" in ts
    assert "+00:00" in ts or ts.endswith("Z")


def test_health_cache_skipped_response():
    """Degraded responses are cached for 30s (matches real probe)."""
    from backend.api.health import get_health, _health_cache

    _health_cache["data"] = None
    _health_cache["at"] = 0.0

    fake_skipped = {
        "stdout": "",
        "stderr": "script not found",
        "returncode": 0,
        "json": None,
        "skipped": True,
    }

    with patch("backend.api.health.run_ps", return_value=fake_skipped) as mock_ps:
        first = get_health()
        # Second call within TTL should hit cache (no second run_ps call)
        second = get_health()

    assert first == second
    # mock_ps called only once due to cache
    assert mock_ps.call_count == 1


def test_health_real_script_passes_through_when_returncode_zero():
    """When script exists and returns JSON, /api/health returns that JSON."""
    from backend.api.health import get_health, _health_cache

    _health_cache["data"] = None
    _health_cache["at"] = 0.0

    fake_ok = {
        "stdout": '{"overall": "green", "checks": []}',
        "stderr": "",
        "returncode": 0,
        "json": {"overall": "green", "checks": []},
    }

    with patch("backend.api.health.run_ps", return_value=fake_ok):
        result = get_health()

    assert result["overall"] == "green"
    assert result["checks"] == []


def test_health_real_script_failure_still_raises_503():
    """When script exists but exits non-zero, /api/health still raises 503."""
    from fastapi import HTTPException

    from backend.api.health import get_health, _health_cache

    _health_cache["data"] = None
    _health_cache["at"] = 0.0

    fake_fail = {
        "stdout": "",
        "stderr": "health probe script error",
        "returncode": 1,
        "json": None,
        # No "skipped" key — script was found but failed
    }

    with patch("backend.api.health.run_ps", return_value=fake_fail):
        try:
            get_health()
            assert False, "expected HTTPException"
        except HTTPException as e:
            assert e.status_code == 503
            assert "health probe failed" in str(e.detail)