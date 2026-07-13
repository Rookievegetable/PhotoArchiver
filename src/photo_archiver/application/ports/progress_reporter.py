"""Progress reporting port for streaming use-case updates."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class ProgressReporter(Protocol):
    """Stream progress updates from a use case to listeners such as worker tasks."""

    def report(self, current: int, total: int, message: str = "") -> None:
        """Report the current progress against the known total.

        Args:
            current: Number of items processed so far (0-based inclusive).
            total: Total number of items to process.
            message: Optional human-readable status message.
        """
        ...
