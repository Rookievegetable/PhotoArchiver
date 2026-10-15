"""AUD-027 方案 B — 仓储持久化前守卫的真实 SQLite 集成测试.

验证跨字段不变量（auto_confirmed ⇒ ordered_auto_confirm；自动来源行不得
confirmed 且 score 恒 NULL）在两条写入路径上于 SQL 执行前拒绝非法组合：

- ``add_assignments``：整批先验后写，任一非法 → 零新增；
- ``update_assignment``：UPDATE 不写 source，最终组合 = **数据库持久化
  source** × 本次写入 status/score——守卫在同一连接内先读后验，并对内存
  source 组合同验（防改内存绕过）；目标行缺失保持既有并发删除语义。

全部使用真实实体/真实仓储/隔离临时库；零 mock。
"""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.domain import (
    ClusterPersonAssignment,
    Person,
    RecognitionRun,
    ValidationError,
)
from photo_archiver.domain.entities.cluster_assignment import (
    ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM,
)

_BASE = datetime(2026, 1, 1, 8, 0, 0)


class _World:
    """真实 FK 链（run → cluster run → cluster）+ 仓储 + 原始 SQL 读取。"""

    def __init__(self, tmp_path: Path):
        self.repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
        self.db = tmp_path / "db.sqlite3"
        self.repos.people.add(Person(name="张三", roster_order=1))
        run = RecognitionRun(parameters={})
        self.repos.recognition_runs.add_run(run)
        from photo_archiver.domain import FaceCluster, FaceClusterRun

        crun = FaceClusterRun(recognition_run_id=run.id, algorithm_version="probe")
        self.repos.face_clusters.add_cluster_run(crun)
        self.cluster_id = crun.id
        self.cluster = FaceCluster(
            cluster_run_id=crun.id, run_id=run.id, ordinal=0, member_count=1,
            sort_key="k|probe|000000", first_captured_at=_BASE)
        self.repos.face_clusters.add_clusters([self.cluster])

    def auto_row(self, *, status="auto_confirmed", source=ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM,
                 score=None):
        row = ClusterPersonAssignment(
            cluster_id=self.cluster.id,
            person_id=self.repos.people.list_all()[0].id,
            source=source, score=score,
        )
        if status == "auto_confirmed":
            row.auto_confirm({"sort_key": "k|probe|000000"})
        return row

    def raw_row(self, row_id):
        conn = sqlite3.connect(str(self.db))
        try:
            conn.row_factory = sqlite3.Row
            return dict(conn.execute(
                "SELECT status, source, score FROM cluster_person_assignments "
                "WHERE id = ?", (str(row_id),)).fetchone())
        finally:
            conn.close()

    def raw_count(self):
        conn = sqlite3.connect(str(self.db))
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM cluster_person_assignments").fetchone()[0]
        finally:
            conn.close()


def test_legal_combinations_round_trip(tmp_path):
    """合法组合（人工 confirmed / 机器 auto_confirmed）写入、更新、读回正常。"""
    world = _World(tmp_path)
    repos = world.repos
    person_id = repos.people.list_all()[0].id
    suggested = ClusterPersonAssignment(
        cluster_id=world.cluster.id, person_id=person_id,
        source="ordered_suggestion")
    repos.cluster_assignments.add_assignments([suggested])
    suggested.confirm({"sort_key": "k"})
    assert repos.cluster_assignments.update_assignment(suggested) == 1
    auto = ClusterPersonAssignment(
        cluster_id=world.cluster.id, person_id=person_id,
        source=ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM)
    auto.auto_confirm({"sort_key": "k"})
    repos.cluster_assignments.add_assignments([auto])
    back_confirmed = repos.cluster_assignments.get_assignment(suggested.id)
    back_auto = repos.cluster_assignments.get_assignment(auto.id)
    assert (back_confirmed.status, back_confirmed.source) == ("confirmed", "ordered_suggestion")
    assert (back_auto.status, back_auto.source, back_auto.score) == (
        "auto_confirmed", ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM, None)
    auto.unassign()
    assert repos.cluster_assignments.update_assignment(auto) == 1
    assert repos.cluster_assignments.get_assignment(auto.id).status == "unassigned"


def test_update_rejects_illegal_status_source_combo_keeps_row_intact(tmp_path):
    """非法组合 UPDATE：领域异常在 SQL 前抛出；DB 行与历史状态不变。"""
    world = _World(tmp_path)
    repos = world.repos
    row = world.auto_row()
    repos.cluster_assignments.add_assignments([row])
    before = world.raw_row(row.id)
    row.status = "confirmed"  # 直改（绕过转换方法）——守卫必须拦在写入前
    with pytest.raises(ValidationError):
        repos.cluster_assignments.update_assignment(row)
    after = world.raw_row(row.id)
    assert after == before  # status/score/source 均未被改动


def test_insert_rejects_illegal_combo_zero_rows(tmp_path):
    """非法组合 INSERT：拒绝且零落库。"""
    world = _World(tmp_path)
    row = world.auto_row()
    row.status = "confirmed"
    with pytest.raises(ValidationError):
        world.repos.cluster_assignments.add_assignments([row])
    assert world.raw_count() == 0


def test_update_rejects_score_on_auto_source_row(tmp_path):
    """非法 score 的 UPDATE：BD-4 违约（伪造相似度证据）在写入前拒绝。"""
    world = _World(tmp_path)
    repos = world.repos
    row = world.auto_row()
    repos.cluster_assignments.add_assignments([row])
    before = world.raw_row(row.id)
    row.score = 0.9
    with pytest.raises(ValidationError):
        repos.cluster_assignments.update_assignment(row)
    assert world.raw_row(row.id) == before


def test_update_validates_against_persisted_source_not_memory(tmp_path):
    """内存 source 与数据库 source 不一致：以持久化组合同验，不得被内存合法值绕过。"""
    world = _World(tmp_path)
    repos = world.repos
    row = world.auto_row()
    repos.cluster_assignments.add_assignments([row])
    before = world.raw_row(row.id)
    # 改内存 source 为合法组合（manual+confirmed）——DB 仍是 ordered_auto_confirm
    row.source = "manual"
    row.status = "confirmed"
    with pytest.raises(ValidationError):
        repos.cluster_assignments.update_assignment(row)
    assert world.raw_row(row.id) == before  # 落库组合仍被 DB source 判非法


def test_update_missing_row_keeps_existing_semantics(tmp_path):
    """目标行不存在：不视作校验通过，保持既有 rowcount=0 并发删除语义。"""
    world = _World(tmp_path)
    repos = world.repos
    row = world.auto_row()  # 从未落库
    assert repos.cluster_assignments.update_assignment(row) == 0


def test_batch_with_illegal_entity_inserts_nothing(tmp_path):
    """批次含非法实体：整批先验后写，零部分新增。"""
    world = _World(tmp_path)
    legal = world.auto_row()
    illegal = world.auto_row()
    illegal.status = "confirmed"
    with pytest.raises(ValidationError):
        world.repos.cluster_assignments.add_assignments([legal, illegal])
    assert world.raw_count() == 0  # 合法实体也未写入（先验后写）


def test_constructor_and_readback_guards_still_fail_closed(tmp_path):
    """不变量回归：构造期守卫与读回 fail-closed 均保持。"""
    world = _World(tmp_path)
    with pytest.raises(ValidationError):
        ClusterPersonAssignment(
            cluster_id=world.cluster.id,
            person_id=world.repos.people.list_all()[0].id,
            source=ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM, status="confirmed",
        )
    with pytest.raises(ValidationError):
        ClusterPersonAssignment(
            cluster_id=world.cluster.id,
            person_id=world.repos.people.list_all()[0].id,
            source=ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM, score=0.5,
        )
    # 直改后经仓储写入被拒 → 读回路径不可能遇到非法行（毒丸行无法产生）。
    repos = world.repos
    row = world.auto_row()
    repos.cluster_assignments.add_assignments([row])
    row.status = "confirmed"
    with pytest.raises(ValidationError):
        repos.cluster_assignments.update_assignment(row)
    assert repos.cluster_assignments.get_assignment(row.id).status == "auto_confirmed"


def test_transition_methods_and_d6_guards_unaffected(tmp_path):
    """转换方法与 D6 守卫：机器保护/人工路径/合法迁移不因守卫回归。"""
    from photo_archiver.application.commands.pairing import UnassignClusterCommand
    from photo_archiver.application.services import PairingWorkbenchService
    from photo_archiver.domain import ManualDecisionProtectedError
    from photo_archiver.domain.entities.cluster_assignment import (
        HUMAN_ACTOR,
        MACHINE_ACTOR,
    )

    world = _World(tmp_path)
    repos = world.repos
    row = world.auto_row()
    repos.cluster_assignments.add_assignments([row])
    workbench = PairingWorkbenchService(
        repos.cluster_assignments, repos.face_clusters, repos.face_observations,
        repos.people, repos.recognition, repos.person_face_samples,
    )
    # D6：机器不得撤销 auto_confirmed（服务层 actor 守卫）。
    with pytest.raises(ManualDecisionProtectedError):
        workbench.unassign(
            UnassignClusterCommand(cluster_id=world.cluster.id),
            actor=MACHINE_ACTOR)
    # 人工解除（合法迁移）→ 读回正常。
    workbench.unassign(
        UnassignClusterCommand(cluster_id=world.cluster.id), actor=HUMAN_ACTOR)
    assert repos.cluster_assignments.get_assignment(row.id).status == "unassigned"
