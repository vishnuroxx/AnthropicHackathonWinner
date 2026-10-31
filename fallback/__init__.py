"""Deterministic non-AI fallback: enumerate recovery plans, check hard rules, return the cheapest valid one."""
from .solver import solve
from .world import FallbackWorld, build_world

__all__ = ["build_world", "solve", "FallbackWorld"]
