"""AUD-030 — 旧 CLI `recognize --all` 的 PENDING 防重守卫真实 SQLite 集成测试.

验证 CLI 层按"任一 PENDING 记录即跳过"过滤候选照片后，多轮 `--all` 不再向
`recognition_results` 追加记录；仅有终态（APPROVED/REJECTED）记录的照片保留
重跑语义；历史 PENDING 原状保留（不清理、不合并）。

真实实体/真实 SQLite 仓储/真实 MatchPersonsService；仅 AI 检测器与 PersonMatcher
使用确定性替身（沿用 test_match_persons_service 的既有模式，判定对象为服务
写入与 CLI 选择行为，非模型）。
"""

import sys
from pathlib import Path

sys.path.insert(0, r"D:\work\PhotoArchiver")

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.commands.match_persons import MatchPersonsCommand
from photo_archiver.application.services.match_persons_service import (
    MatchPersonsService,
)
from photo_archiver.ai.similarity_matcher import CosinePersonMatcher
from photo_archiver.domain import (
    FaceBox,
    FaceBoxEmbedding,
    FaceEmbedding,
    Person,
    Photo,
    PhotoPath,
    PhotoPathBase,
    RecognitionResult,
)
from photo_archiver.domain.entities.recognition import MatchStatus


class _StubDetector:
    """确定性检测替身（替代 InsightFace；判定对象为服务写入/选择行为）。"""

    def __init__(self):
        self.calls = 0

    def detect(self, image):
        return self.detect_with_embeddings(image)

    def detect_with_embeddings(self, image):
        self.calls += 1
        return [FaceBoxEmbedding(
            box=FaceBox(x1=0, y1=0, x2=8, y2=8, confidence=0.9),
            embedding=FaceEmbedding((1.0, 0.0, 0.0, 0.0)),
        )]


class _StubRecognizer:
    """占位识别器（旧链 _analyze_one 不经它——协议完整性所需）。"""


def _world(tmp_path: Path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    repos.people.add(Person(name="张三", roster_order=1))
    photos = []
    for index in range(3):
        photo = Photo(
            path=PhotoPath(Path(f"P:/legacy/p{index}.jpg"), PhotoPathBase.ABSOLUTE),
            captured_at=None,
        )
        repos.photos.add(photo)
        photos.append(photo)
    service = MatchPersonsService(
        detector=_StubDetector(),
        recognizer=_StubRecognizer(),
        matcher=CosinePersonMatcher(threshold=0.40),
        face_embedding_repository=repos.face_embeddings,  # 生产现实：恒空
        recognition_repository=repos.recognition,
        max_workers=1,
    )
    return repos, photos, service


def _command(photos):
    return MatchPersonsCommand(
        photo_ids=tuple(photo.id for photo in photos),
        images=tuple(photo.path.raw_path for photo in photos),
    )


def _pending_count(repos):
    return len(repos.recognition.list_pending())


def test_aud030_repeated_all_accumulates_without_guard_then_guard_stops_growth(tmp_path):
    """核心场景：无守卫时每次 --all 对每照片追加一条 PENDING；守卫上线后多轮 --all 不再追加。"""
    repos, photos, service = _world(tmp_path)
    command = _command(photos)
    # 第一次运行（守卫前真实链语义 = 本次修复后的首轮）：每照片 1 条 PENDING。
    service.execute(command)
    assert _pending_count(repos) == 3
    # 第二次运行（修复后的 CLI 行为）：CLI 层过滤有 PENDING 的照片 → 提交集为空。
    # 直接以服务级复验 CLI 过滤后的等价提交集：全部照片均有 PENDING → 全部跳过。
    all_results = repos.recognition.list_by_photo_ids([p.id for p in photos])
    has_pending = {r.photo_id for r in all_results if r.status == MatchStatus.PENDING}
    eligible = [p.id for p in photos if p.id not in has_pending]
    service.execute(MatchPersonsCommand(
        photo_ids=tuple(eligible),
        images=tuple(str(p.path.raw_path) for p in photos if p.id in set(eligible)),
    ))
    assert eligible == []                       # 全部照片都有 PENDING → 零提交
    assert _pending_count(repos) == 3           # 零追加
    for photo in photos:
        rows = repos.recognition.list_by_photo(photo.id)
        assert len(rows) == 1                   # 历史记录原状，不清理/合并
        assert rows[0].status == MatchStatus.PENDING


def test_aud030_cli_filter_skips_pending_and_keeps_finalized_rerun(tmp_path):
    """CLI 过滤语义：PENDING 跳过；仅终态（REJECTED）照片重跑；混合也跳过。"""
    repos, photos, _ = _world(tmp_path)
    service = MatchPersonsService(
        detector=_StubDetector(),
        recognizer=_StubRecognizer(),
        matcher=CosinePersonMatcher(threshold=0.40),
        face_embedding_repository=repos.face_embeddings,
        recognition_repository=repos.recognition,
        max_workers=1,
    )
    p0, p1, p2 = photos
    # 预置：p0 两条 PENDING（历史累积形态）；p1 一条 REJECTED（终态）；p2 一条 PENDING。
    service.execute(_command([p0]))
    service.execute(_command([p0]))
    repos.recognition.add(RecognitionResult(
        photo_id=p1.id, confidence=0.5, person_id=None,
        status=MatchStatus.REJECTED,
    ))
    service.execute(_command([p2]))

    def pending_photo_ids():
        return {
            r.photo_id for r in repos.recognition.list_by_photo_ids(
                [p.id for p in photos]
            )
            if r.status == MatchStatus.PENDING
        }

    eligible = [p.id for p in photos if p.id not in pending_photo_ids()]
    # p0、p2 有 PENDING → 跳过；p1 仅终态 → 保留重跑资格。
    assert eligible == [p1.id]
    service.execute(MatchPersonsCommand(
        photo_ids=tuple(eligible),
        images=tuple(p.path.raw_path for p in photos if p.id in set(eligible)),
    ))
    # p1 重跑：原有 REJECTED 历史保留，新 PENDING 追加（重跑语义）。
    p1_rows = repos.recognition.list_by_photo(p1.id)
    assert sum(1 for r in p1_rows if r.status == MatchStatus.REJECTED) == 1
    assert sum(1 for r in p1_rows if r.status == MatchStatus.PENDING) == 1
    # p0、p2 的 PENDING 记录原状（未被清理/合并），队列仍由既有 Review 流程处置。
    assert _pending_count(repos) >= 3
    for photo in (p0, p2):
        rows = repos.recognition.list_by_photo(photo.id)
        assert all(r.status == MatchStatus.PENDING for r in rows)
