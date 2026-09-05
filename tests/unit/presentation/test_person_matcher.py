"""person_matcher 排名守护测试（人员下拉智能搜索，2026-09-05 UI 轮）.

owner 规格以查询 ``ab`` 锁定四级优先级（自左向右）：
全等 ``ab`` → 前缀 ``abxxx`` → 连续包含按首现位置（``xabx`` → ``xxab``）→
子序列按最小窗口跨度（``axbx`` → ``axxb``）。此处逐条验收该排序，另覆盖
单字包含、大小写、空查询、无匹配排除与确定性。
"""

from photo_archiver.presentation.person_matcher import rank_person_names


def test_owner_spec_ab_ranks_six_tiers_in_order() -> None:
    """owner 规格验收：输入 ab 的六级排序自左向右一一对应。"""
    names = ["axxb", "xxab", "abxxx", "xabx", "ba", "axbx", "ab", "aXb"]  # 打乱输入
    assert rank_person_names("ab", names) == [
        "ab",      # 全等
        "abxxx",   # 前缀
        "xabx",    # 连续包含，首现位置 1
        "xxab",    # 连续包含，首现位置 2
        "aXb",     # 子序列，跨度 2（与 axbx 同级）→ 层内按名称字典序靠前
        "axbx",    # 子序列，最小窗口跨度 2
        "axxb",    # 子序列，最小窗口跨度 3
    ]


def test_single_character_filters_by_containment() -> None:
    """输入一个字：包含该字的人员全部命中，且"陈10号"不含"9"被排除。"""
    names = ["陈1号", "陈10号", "陈2号", "王五"]
    assert rank_person_names("1", names) == ["陈10号", "陈1号"]  # 同级并列按名称字典序
    assert rank_person_names("陈", names) == ["陈10号", "陈1号", "陈2号"]
    assert rank_person_names("9", names) == []


def test_two_characters_require_containment_or_subsequence() -> None:
    """输入两字：连续包含优先于拆开的子序列；顺序颠倒不算命中。"""
    names = ["张伟", "张三伟", "伟张", "李四"]
    assert rank_person_names("张伟", names) == [
        "张伟",     # 全等
        "张三伟",   # 子序列（张…伟 按序），跨度更小者靠前
    ]


def test_subsequence_prefers_compact_window_over_early_start() -> None:
    """aXaXaXb 型：贪心最早匹配给起点 0（跨度 6），最小窗口 DP 给 (2,6)——
    "aab" 需要两个 a，窗口必须同时盖住 a@2 与 a@4。"""
    from photo_archiver.presentation.person_matcher import _minimal_subsequence_window

    assert _minimal_subsequence_window("aXaXaXb", "aab") == (2, 6)
    assert rank_person_names("aab", ["aXaXaXb"]) == ["aXaXaXb"]


def test_case_insensitive_matching() -> None:
    names = ["Alice", "BOB", "alice2"]
    assert rank_person_names("ali", names) == ["Alice", "alice2"]
    assert rank_person_names("ALICE", names) == ["Alice", "alice2"]


def test_empty_query_matches_nothing() -> None:
    assert rank_person_names("", ["陈1号"]) == []
    assert rank_person_names("   ", ["陈1号"]) == []


def test_duplicates_preserved_and_deterministic() -> None:
    """同名条目逐条保留，排序稳定可复现。"""
    names = ["陈1号", "陈1号", "陈2号"]
    assert rank_person_names("陈", names) == ["陈1号", "陈1号", "陈2号"]
    assert rank_person_names("陈", list(reversed(names))) == [
        "陈1号",
        "陈1号",
        "陈2号",
    ]
