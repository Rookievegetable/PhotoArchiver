"""Recognition run use case boundary."""

from photo_archiver.application.commands.start_recognition_run import StartRecognitionRunCommand
from photo_archiver.domain import RecognitionRun


class RunRecognitionUseCase:
    """Define the traceable recognition-run workflow."""

    def execute(self, command: StartRecognitionRunCommand) -> RecognitionRun:
        raise NotImplementedError

    def cancel(self) -> None:
        """Request cooperative cancellation of the active run."""
        raise NotImplementedError
