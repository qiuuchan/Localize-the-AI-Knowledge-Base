"""Agent package (v2.0).

Tool registry + ReAct loop + trajectory persistence for tool-calling agents.

PR#1 ships tools, PR#2 adds the loop; trajectory.py lands in PR#3.
"""
from __future__ import annotations

from backend.core.agent.loop import run_agent
from backend.core.agent.tools import TOOLS, execute_tool

__all__ = ["TOOLS", "execute_tool", "run_agent"]
