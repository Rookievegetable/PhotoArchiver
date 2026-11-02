"""照片墙「归档到该人员」选区门（追加轮 31，Owner）.

单脸硬前提前置：**任一张选中照片不满足条件（多人脸/无人脸等）＝入口直接
禁用**（tooltip 说明原因）；单选单脸未匹配照片＝可用。真实 bootstrap +
真实 SQLite（冒烟同构），不弹模态。
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from pathlib import Path

from photo_archiver.app import bootstrap_application
from photo_archiver.domain import (
    FaceBox,
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
    FaceEmbedding,
    FaceObservation,
    Photo,
    PhotoPath,
    PhotoPathBase,
    RecognitionRun,
)
from photo_archiver.infrastructure.config import AppSettings
from photo_archiver.presentation.views.main_window import MainWindow


def _seed(tmp_path: Path):
    """两张未匹配照片：single＝1 张脸（可归档）；multi＝2 张脸（应禁用）。"""
    settings = AppSettings(database_url=f"sqlite:///{tmp_path / 'gate.db'}")
    settings.ensure_runtime_directories()
    context = bootstrap_application(settings)
    repos = context.repositories
    run = RecognitionRun(parameters={})
    repos.recognition_runs.add_run(run)
    cluster_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="t")
    repos.face_clusters.add_cluster_run(cluster_run)

    photos = {}
    for name, faces in (("single.jpg", 1), ("multi.jpg", 2)):
        photo_file = tmp_path / name
        photo_file.write_bytes(b"x")
        photo = Photo(
            path=PhotoPath(photo_file, base=PhotoPathBase.ABSOLUTE),
            original_name=name,
        )
        repos.photos.add(photo)
        photos[name] = photo
        cluster = FaceCluster(
            cluster_run_id=cluster_run.id, run_id=run.id,
            ordinal=len(photos), member_count=faces, sort_key=f"k|{name}",
        )
        repos.face_clusters.add_clusters([cluster])
        observations = [
            FaceObservation(
                run_id=run.id, photo_id=photo.id, face_index=index,
                photo_face_count=faces, det_score=0.9, box=FaceBox(0, 0, 9, 9),
                embedding=FaceEmbedding((1.0, float(index))),
                scope_verdict="in_selected_scope",
            )
            for index in range(faces)
        ]
        repos.face_observations.add_many(observations)
        repos.face_clusters.add_members([
            FaceClusterMember(cluster_id=cluster.id, observation_id=o.id)
            for o in observations
        ])
    return context, photos


def _row_of(window, photo_id) -> int:
    # _photos_by_id 插入序＝load_photos 行序（模型无公开照片访问器）。
    return list(window._photos_by_id).index(photo_id)


def test_wall_gate_disables_attribution_for_multi_face_selection(
    qtbot, tmp_path: Path,
) -> None:
    context, photos = _seed(tmp_path)
    window = MainWindow(context)
    qtbot.addWidget(window)
    window._refresh_photo_list()

    from photo_archiver.presentation.visual_style import ROLE_SUCCESS, button_role

    button = window._manual_attribution_button
    assert button_role(button) == ROLE_SUCCESS  # 追加轮 32：可用态绿色
    single_row = _row_of(window, photos["single.jpg"].id)
    multi_row = _row_of(window, photos["multi.jpg"].id)

    # 单选单脸未匹配照片 → 可用（基础 tooltip）
    window._photo_list.selectionModel().select(
        window._photo_list_model.index(single_row, 0),
        window._photo_list.selectionModel().SelectionFlag.ClearAndSelect
        | window._photo_list.selectionModel().SelectionFlag.Rows,
    )
    window._update_bulk_bar()
    assert button.isEnabled() is True
    assert "只支持只有一张人脸" in button.toolTip()

    # 单选多人脸照片 → 直接禁用 + 原因入 tooltip
    window._photo_list.selectionModel().select(
        window._photo_list_model.index(multi_row, 0),
        window._photo_list.selectionModel().SelectionFlag.ClearAndSelect
        | window._photo_list.selectionModel().SelectionFlag.Rows,
    )
    window._update_bulk_bar()
    assert button.isEnabled() is False
    assert "张人脸" in button.toolTip()

    # 混合选区（单脸+多人脸）→ 任一张不满足即禁用
    selection = window._photo_list.selectionModel()
    selection.select(
        window._photo_list_model.index(single_row, 0),
        selection.SelectionFlag.Select | selection.SelectionFlag.Rows,
    )
    window._update_bulk_bar()
    assert button.isEnabled() is False

    # 回到纯单脸选区 → 恢复
    window._photo_list.selectionModel().select(
        window._photo_list_model.index(single_row, 0),
        selection.SelectionFlag.ClearAndSelect | selection.SelectionFlag.Rows,
    )
    window._update_bulk_bar()
    assert button.isEnabled() is True
