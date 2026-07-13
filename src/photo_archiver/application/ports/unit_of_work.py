"""Unit of work port for transactional use-case boundaries."""

from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable, TypeVar

T = TypeVar("T")


@runtime_checkable
class UnitOfWork(Protocol):
    """Define a transactional scope for use cases that need atomic persistence.

    Implementations enter a transaction on ``__enter__`` and commit on normal
    exit or roll back on exception. Use cases receive this port to wrap a batch
    of repository calls without knowing the underlying persistence technology.
    """

    def __enter__(self) -> "UnitOfWork":
        """Begin the transactional scope and return the unit of work."""
        ...

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Commit on normal exit or roll back on exception."""
        ...
