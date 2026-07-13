"""Use case boundary for registering photos."""

from typing import Protocol

from photo_archiver.application.commands import RegisterPhotoCommand
from photo_archiver.application.dtos import RegisterPhotoResult


class RegisterPhotoUseCase(Protocol):
    """Register a discovered photo in the archive catalog."""

    def execute(self, command: RegisterPhotoCommand) -> RegisterPhotoResult:
        """Run the photo registration workflow."""