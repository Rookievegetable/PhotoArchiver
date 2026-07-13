"""Use case boundary for importing people."""

from typing import Protocol

from photo_archiver.application.commands import ImportPeopleCommand
from photo_archiver.application.dtos import ImportPeopleResult


class ImportPeopleUseCase(Protocol):
    """Import people into the archive catalog."""

    def execute(self, command: ImportPeopleCommand) -> ImportPeopleResult:
        """Run the people import workflow."""