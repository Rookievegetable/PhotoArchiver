"""List recognition runs service — D-4 聚类入口的识别运行选择数据源.

薄读用例（同 ``ListPersonsService`` 模式）：把
``RecognitionRunRepository.list_runs()``（created_at 降序、id 升序并列）
交给展示层填充运行选择器。零业务决策。
"""

from loguru import logger

from photo_archiver.domain import RecognitionRun, RecognitionRunRepository


class ListRecognitionRunsService:
    """Expose recognition runs for the clustering entry's run selector."""

    def __init__(self, recognition_run_repository: RecognitionRunRepository) -> None:
        """Initialize with the recognition run repository to read."""
        self._run_repository = recognition_run_repository

    def execute(self) -> list[RecognitionRun]:
        """Return all recognition runs, newest first (repository order)."""
        runs = self._run_repository.list_runs()
        logger.info("ListRecognitionRunsService: {} run(s) available", len(runs))
        return runs
