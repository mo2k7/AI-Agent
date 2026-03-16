"""Result type for error handling at architectural boundaries.

Replaces raw exception propagation across module boundaries with explicit
Success/Failure returns.  Internal code may still use exceptions; the
Result type is for BOUNDARY crossings only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar, Union

T = TypeVar("T")
U = TypeVar("U")


@dataclass(frozen=True, slots=True)
class Success(Generic[T]):
    """Successful result containing a value."""

    value: T

    @property
    def is_ok(self) -> bool:
        return True

    @property
    def is_err(self) -> bool:
        return False

    def map(self, fn: Callable[[T], U]) -> Result[U]:
        return Success(fn(self.value))

    def flat_map(self, fn: Callable[[T], Result[U]]) -> Result[U]:
        return fn(self.value)

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value


@dataclass(frozen=True, slots=True)
class Failure:
    """Failed result containing an AgentError."""

    error: Any  # AgentError — uses Any to avoid circular import

    @property
    def is_ok(self) -> bool:
        return False

    @property
    def is_err(self) -> bool:
        return True

    def map(self, fn: Callable) -> Failure:
        return self

    def flat_map(self, fn: Callable) -> Failure:
        return self

    def unwrap(self) -> Any:
        raise ValueError(f"Called unwrap() on a Failure: {self.error}")

    def unwrap_or(self, default: T) -> T:
        return default


# The union type used in type annotations
Result = Union[Success[T], Failure]
