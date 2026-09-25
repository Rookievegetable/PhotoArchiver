"""ClusterFacesTask worker tests — task naming, progress and cancel propagation."""

from uuid import uuid4

import pytest

from photo_archiver.application import StartClusteringRunCommand
from photo_archiver.workers import ClusterFacesTask
from photo_archiver.workers.events import TaskCancelled, TaskCompleted, TaskProgress, TaskStarted


class _StubUseCase:
    def __init__(self):
        self.cancelled = False
        self.commands = []

    def execute(self, command):
        self.commands.append(command)
        return "cluster-run"

    def cancel(self):
        self.cancelled = True


def test_task_name_and_lifecycle_events():
    use_case = _StubUseCase()
    command = StartClusteringRunCommand(uuid4())
    task = ClusterFacesTask(use_case, command)
    events = []
    task.subscribe(events.append)

    result = task.run()

    assert result == "cluster-run"
    assert task.name == "face_clustering"
    # stub 无 bind_progress_reporter → 无 binder 分支：粗进度一条 + 完成标记。
    assert [type(event) for event in events] == [
        TaskStarted, TaskProgress, TaskCompleted,
    ]
    assert use_case.commands == [command]


def test_cancel_propagates_to_use_case():
    use_case = _StubUseCase()
    command = StartClusteringRunCommand(uuid4())
    task = ClusterFacesTask(use_case, command)
    events = []
    task.subscribe(events.append)
    task.cancel("stop clustering")

    with pytest.raises(Exception, match="stop clustering"):
        task.run()

    assert use_case.cancelled is True
    assert [type(event) for event in events] == [TaskStarted, TaskCancelled]
