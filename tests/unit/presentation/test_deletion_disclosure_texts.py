"""界面优化 P2/P3 — 三入口删除披露口径一致性（文案层）.

验收锚（阶段 1 任务书 §1.1/§1.2/§4）：单人/按批次/清空三个删除入口都必须
披露 ①身份决策历史级联、②多样本库级联，且计数进入文案与完成消息——任何
一处漏披露即失败。
"""

from photo_archiver.application.dtos.deletion import BatchRosterDeletionResult
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.views.batch_person_deletion_dialog import (
    _result_message,
)


def test_all_three_entries_disclose_decisions_and_samples() -> None:
    """三入口影响文案同时包含决策历史与多样本库披露及计数占位。"""
    for template in (
        text.PERSON_DELETE_CONFIRM,
        text.BATCH_DELETE_IMPACT,
        text.CLEAR_ALL_IMPACT,
    ):
        assert "决策历史" in template
        assert "人脸样本" in template
        assert "{assignment_count}" in template
        assert "{sample_count}" in template


def test_impact_texts_render_real_counts() -> None:
    """格式化后计数可见（不是占位符残留）。"""
    person_text = text.PERSON_DELETE_CONFIRM.format(
        name="张三", assignment_count=7, sample_count=11,
        embedding_count=2, recognition_count=3,
    )
    assert "7 条身份决策历史" in person_text
    assert "11 条人脸样本" in person_text

    batch_text = text.BATCH_DELETE_IMPACT.format(
        person_count=36, names="张三", assignment_count=36, sample_count=405,
        embedding_count=10, recognition_count=5,
    )
    assert "36 条身份决策历史" in batch_text
    assert "405 条人脸样本" in batch_text

    clear_text = text.CLEAR_ALL_IMPACT.format(
        person_count=36, names="张三", assignment_count=36, sample_count=405,
        embedding_count=10, recognition_count=5,
    )
    assert "36 条身份决策历史" in clear_text
    assert "405 条人脸样本" in clear_text


def test_done_messages_carry_cascade_counts() -> None:
    """完成消息同样如实报告级联数量（与预览口径同源）。"""
    person_done = text.PERSON_DELETE_DONE.format(
        name="张三", assignment_cascade=7, sample_cascade=11,
        embedding_cascade=2, recognition_orphaned=3,
    )
    assert "决策历史 7 条" in person_done
    assert "样本 11 条" in person_done

    result = BatchRosterDeletionResult(
        requested=1, removed=1, missing=0,
        embedding_cascade=2, recognition_orphaned=3,
        batch_record_deleted=0, draft_rows_deleted=0,
        assignment_cascade=7, sample_cascade=11,
    )
    batch_done = _result_message(result, batch_name="名单_test.txt")
    assert "决策历史 7 条" in batch_done
    assert "样本 11 条" in batch_done

    clear_done = _result_message(result, batch_name="")
    assert "决策历史 7 条" in clear_done
    assert "样本 11 条" in clear_done
