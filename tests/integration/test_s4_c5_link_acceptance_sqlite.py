"""S4 C-5 — 场景 4/8 全链集成验收（正式 C-5 场景矩阵补齐）.

场景 4（数量不一致 + 高分样本匹配）：先人工确认 1 簇建样本，再对新代际跑
建议 → sample_match 正常生成、剩余集数量不等 → **整批**位置自动确认被阻断
（0 auto_confirmed），既有 suggested 行为保留（D3=A）——高分证据不得突破
批次保护。
场景 8（auto_confirmed 起点全链一致）：自动确认批次的终审/拒绝/改派/解除
与重跑——决策历史、样本、投影、归档可见性按 reconciler 支撑重算一致
（S1 模式；D4 拒绝对阻断 + 规则③既有顺延过滤语义）。

真实 SQLite + 真实仓储 + 真实应用服务（AI 检测器以可控假检测器替代，
与 AUD-004 同约定）；复用 AUD-004 全链助手，不重建等价框架。
"""

from datetime import datetime

import pytest

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.commands.pairing import (
    AssignClusterPersonCommand,
    RejectAssignmentCommand,
    UnassignClusterCommand,
)
from photo_archiver.domain.entities.cluster_assignment import HUMAN_ACTOR
from photo_archiver.domain.services.positional_auto_confirm import (
    ADMISSION_REASON_COUNT_MISMATCH,
    ADMISSION_REASON_REJECTED_POSITIONAL_PAIR,
)

from tests.integration.test_aud004_full_chain_regression import (
    V_A,
    V_B,
    _FakeDetector,
    _cluster,
    _cluster_photo_names,
    _confirm_all,
    _import_roster,
    _make_image,
    _recognize,
    _scan,
    _suggest,
    _workbench,
)


def _rows(repos, cluster_run):
    return repos.cluster_assignments.list_by_cluster_run(cluster_run.id)


def _photo_id(repos, name):
    return next(p.id for p in repos.photos.list_all() if p.original_name == name)


def _cluster_by_photo(repos, run, cluster_run, name):
    photo_by_cluster = _cluster_photo_names(repos, run, cluster_run)
    return next(
        cluster for cluster in repos.face_clusters.list_clusters(cluster_run.id)
        if photo_by_cluster[cluster.id] == name
    )


def test_scenario4_count_mismatch_with_high_score_sample_match(tmp_path):
    """场景 4：sample_match 消耗后剩余集数量不等 → 整批不自动确认（D3=A）。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    _make_image(photos_dir, "gen1.jpg", datetime(2026, 1, 1, 12, 0, 0))
    detector1 = _FakeDetector({"gen1.jpg": [(0.9, V_A), (0.9, V_A)]})
    persons = _import_roster(
        repos, tmp_path,
        [("张三", "E001", ""), ("李四", "E002", ""), ("王五", "E003", "")],
    )
    zhang = persons[0]
    _, photos = _scan(repos, photos_dir)
    run1 = _recognize(repos, detector1, photos)
    cluster_run1 = _cluster(repos, run1)                  # 同向量 → 1 簇 2 成员
    # gen1：1 簇 × 3 人 → 数量不等 → suggested 路径（非本场景重点，作为样本来源前置）
    summary1 = _suggest(repos, cluster_run1)
    assert summary1.auto_confirmed == 0
    assert summary1.auto_confirm_blocked_reason == ADMISSION_REASON_COUNT_MISMATCH
    # 人工确认唯一簇 → 张三沉淀 2 个真样本（gen2 高分匹配的证据来源）
    confirmed = _confirm_all(repos, cluster_run1)
    assert len(confirmed) == 1 and confirmed[0].samples_written == 2

    # gen2：两张新照片 → 2 簇；rule① 命中 1（张三），剩余 1 簇 × 2 人
    _make_image(photos_dir, "gen2a.jpg", datetime(2026, 2, 1, 12, 0, 0))
    _make_image(photos_dir, "gen2b.jpg", datetime(2026, 3, 1, 12, 0, 0))
    _, all_photos = _scan(repos, photos_dir)              # 登记新照片（重扫幂等）
    detector2 = _FakeDetector({"gen2a.jpg": [(0.9, V_A)], "gen2b.jpg": [(0.9, V_B)]})
    new_photos = [
        photo for photo in all_photos
        if photo.original_name in ("gen2a.jpg", "gen2b.jpg")
    ]
    run2 = _recognize(repos, detector2, new_photos)
    cluster_run2 = _cluster(repos, run2)
    assert len(repos.face_clusters.list_clusters(cluster_run2.id)) == 2

    summary2 = _suggest(repos, cluster_run2)

    # 批次保护（D3=A）：高分样本匹配不得突破整批数量保护
    assert summary2.auto_confirmed == 0
    assert summary2.auto_confirm_blocked_reason == ADMISSION_REASON_COUNT_MISMATCH
    assert summary2.sample_matched == 1 and summary2.ordered == 1
    rows2 = {row.cluster_id: row for row in _rows(repos, cluster_run2)}
    assert len(rows2) == 2
    assert {row.status for row in rows2.values()} == {"suggested"}
    by_source = {}
    for row in rows2.values():
        by_source.setdefault(row.source, []).append(row)
    matched = by_source["sample_match"][0]
    assert matched.person_id == zhang.id
    assert matched.score == pytest.approx(1.0)            # 真实余弦，非伪造
    ordered = by_source["ordered_suggestion"][0]
    assert ordered.score is None and ordered.person_id != zhang.id
    assert not [row for row in rows2.values() if row.status == "auto_confirmed"]
    # gen1 历史未被重跑覆盖；建议不沉淀样本
    assert all(row.status == "confirmed" for row in _rows(repos, cluster_run1))
    assert len(repos.person_face_samples.list_by_person(zhang.id)) == 2
    for person in persons[1:]:
        assert repos.person_face_samples.list_by_person(person.id) == []


def test_scenario8_auto_origin_full_chain_consistency(tmp_path):
    """场景 8：auto_confirmed 起点的终审/拒绝/改派/解除/重跑全链一致。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    _make_image(photos_dir, "alpha.jpg", datetime(2026, 1, 1, 12, 0, 0))
    _make_image(photos_dir, "beta.jpg", datetime(2026, 2, 1, 12, 0, 0))
    detector = _FakeDetector({"alpha.jpg": [(0.9, V_A)], "beta.jpg": [(0.9, V_B)]})
    persons = _import_roster(
        repos, tmp_path, [("张三", "E001", ""), ("李四", "E002", "")],
    )
    zhang, li = persons
    _, photos = _scan(repos, photos_dir)
    run = _recognize(repos, detector, photos)
    cluster_run = _cluster(repos, run)
    alpha = _cluster_by_photo(repos, run, cluster_run, "alpha.jpg")
    beta = _cluster_by_photo(repos, run, cluster_run, "beta.jpg")
    photo_alpha = _photo_id(repos, "alpha.jpg")
    photo_beta = _photo_id(repos, "beta.jpg")
    workbench = _workbench(repos)

    # 整批位置自动确认（2×2 相等、时间齐备、无拒绝对）
    summary = _suggest(repos, cluster_run)
    assert summary.auto_confirmed == 2
    rows = {row.cluster_id: row for row in _rows(repos, cluster_run)}
    assert all(row.source == "ordered_auto_confirm" and row.score is None
               for row in rows.values())
    # 终审前：零样本 / 零投影 / 零归档可见性（BD-5/D1=A）
    assert repos.person_face_samples.list_enabled() == []
    assert repos.recognition.list_projections() == []
    assert repos.recognition.read_workspace_counts().archivable_count == 0

    # 人工终审 α（D6 路径：退休 auto 行 + 新建 manual confirmed）→ 样本 + 投影
    final = workbench.assign_person(AssignClusterPersonCommand(
        cluster_id=alpha.id, person_id=rows[alpha.id].person_id),
        actor=HUMAN_ACTOR)
    assert final.status == "confirmed" and final.samples_written == 1
    alpha_latest = repos.cluster_assignments.list_latest_decision(alpha.id)
    assert alpha_latest.status == "confirmed" and alpha_latest.source == "manual"
    assert repos.recognition.find_projection(photo_alpha, rows[alpha.id].person_id) is not None

    # β 人工拒绝（auto_confirmed → rejected 同行迁移；auto 行从不产生投影）
    beta_auto = rows[beta.id]
    workbench.reject(RejectAssignmentCommand(beta_auto.id), actor=HUMAN_ACTOR)
    assert repos.cluster_assignments.get_assignment(beta_auto.id).status == "rejected"
    assert repos.recognition.find_projection(photo_beta, beta_auto.person_id) is None
    assert repos.recognition.read_workspace_counts().archivable_count == 1

    # 决策历史：α = [auto(退休), manual(确认)]；β = [rejected]
    alpha_history = [row.status for row in
                     repos.cluster_assignments.list_by_cluster(alpha.id)]
    assert sorted(alpha_history) == ["confirmed", "unassigned"]
    assert [row.status for row in
            repos.cluster_assignments.list_by_cluster(beta.id)] == ["rejected"]

    # 同代际重跑：α 被活动行跳过、张三身份已占 → 剩余 (β)×(李四) = 拒绝对 → D4 阻断
    summary_r1 = _suggest(repos, cluster_run)
    assert summary_r1.auto_confirmed == 0
    assert summary_r1.auto_confirm_blocked_reason == ADMISSION_REASON_REJECTED_POSITIONAL_PAIR
    assert summary_r1.suggestions == 0
    assert len(_rows(repos, cluster_run)) == 3            # 零新行（幂等不覆盖）

    # 改派：α 张三 → 李四（旧 manual 行退休 + 新 manual 行；投影重定向；样本重指）
    reassign = workbench.assign_person(AssignClusterPersonCommand(
        cluster_id=alpha.id, person_id=li.id),
        actor=HUMAN_ACTOR)
    assert reassign.status == "confirmed"
    assert repos.recognition.find_projection(photo_alpha, li.id) is not None
    assert repos.recognition.find_projection(photo_alpha, zhang.id) is None
    enabled_owners = {
        sample.person_id for sample in repos.person_face_samples.list_enabled()
    }
    assert zhang.id not in enabled_owners                 # 旧身份样本停用
    assert len([s for s in repos.person_face_samples.list_enabled()
                if s.person_id == li.id]) == 1
    assert repos.recognition.read_workspace_counts().archivable_count == 1

    # 解除：α → unassigned → 投影终结 → 可归档清零
    workbench.unassign(UnassignClusterCommand(alpha.id), actor=HUMAN_ACTOR)
    assert repos.recognition.read_workspace_counts().archivable_count == 0
    assert repos.recognition.find_projection(photo_alpha, li.id) is None

    # 重跑一致：α 无活动行、β rejected → 2 簇 × 2 人相等但 (β,李四) 被拒 → 阻断；
    # 既有规则③顺延过滤语义：α×张三 suggested、β 无建议
    summary_r2 = _suggest(repos, cluster_run)
    assert summary_r2.auto_confirmed == 0
    assert summary_r2.auto_confirm_blocked_reason == ADMISSION_REASON_REJECTED_POSITIONAL_PAIR
    suggested = [row for row in _rows(repos, cluster_run) if row.status == "suggested"]
    assert len(suggested) == 1
    assert suggested[0].cluster_id == alpha.id
    assert suggested[0].person_id == zhang.id
