"""Use case boundary for face clustering（阶段 D 第一阶段）."""

from photo_archiver.application.commands.cluster_faces import StartClusteringRunCommand
from photo_archiver.domain import FaceClusterRun


class ClusterFacesUseCase:
    """Define the traceable face-clustering workflow (rerunnable per recognition run)."""

    def execute(self, command: StartClusteringRunCommand) -> FaceClusterRun:
        raise NotImplementedError

    def cancel(self) -> None:
        """Request cooperative cancellation of the in-flight clustering."""
        raise NotImplementedError
