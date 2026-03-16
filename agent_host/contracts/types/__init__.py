"""Shared domain types, value objects, and result types.

All types defined here are framework-agnostic and have zero external
dependencies beyond the Python standard library.
"""

from agent_host.contracts.types.result import Result, Success, Failure
from agent_host.contracts.types.errors import AgentError, ErrorCode

__all__ = [
    "Result",
    "Success",
    "Failure",
    "AgentError",
    "ErrorCode",
]
