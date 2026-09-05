"""人员名称智能匹配排名（人员下拉搜索，2026-09-05 UI 轮）.

纯函数、零 Qt 依赖——给 ``FilterBar`` 的人员搜索补全器提供"匹配 + 排序"，
语义由 owner 规格锁定（以查询 ``ab`` 为验收例，优先级自左向右）：

1. 全等：名称 == ``ab``；
2. 前缀：名称以 ``ab`` 开头（``abxxx``）；
3. 连续包含：名称含连续 ``ab``——按首次出现位置自左向右排序
   （``xabx`` 先于 ``xxab``）；
4. 子序列：``a``、``b`` 按序出现但不连续——按最小窗口跨度排序，跨度相同
   按窗口起点（``axbx`` 先于 ``axxb``）。

不含查询串的名称被排除。大小写不敏感（casefold）。同层内按名称稳定排序，
保证同输入同输出。
"""

from __future__ import annotations

from collections.abc import Sequence

_TIER_EXACT = 0
_TIER_PREFIX = 1
_TIER_CONTAINS = 2
_TIER_SUBSEQUENCE = 3


def rank_person_names(query: str, names: Sequence[str]) -> list[str]:
    """Return the names matching ``query``, sorted in smart rank order.

    Args:
        query: The search text typed by the user; empty/whitespace matches
            nothing (the caller shows the full list instead).
        names: All available person names (may contain duplicates — the
            result preserves one entry per input occurrence).

    Returns:
        Matching names in rank order (exact → prefix → contains →
        subsequence), ties broken deterministically.
    """
    needle = query.strip().casefold()
    if not needle:
        return []
    ranked: list[tuple[int, int, int, str]] = []
    for name in names:
        key = _match_key(needle, name.casefold())
        if key is not None:
            ranked.append((*key, name))
    ranked.sort()
    return [name for _, _, _, name in ranked]


def _match_key(needle: str, haystack: str) -> tuple[int, int, int] | None:
    """Ranking key for one folded name against the folded query, or ``None``."""
    if haystack == needle:
        return (_TIER_EXACT, 0, 0)
    if haystack.startswith(needle):
        return (_TIER_PREFIX, 0, 0)
    index = haystack.find(needle)
    if index >= 0:
        return (_TIER_CONTAINS, index, 0)
    window = _minimal_subsequence_window(haystack, needle)
    if window is not None:
        start, end = window
        return (_TIER_SUBSEQUENCE, end - start, start)
    return None


def _minimal_subsequence_window(
    haystack: str, needle: str
) -> tuple[int, int] | None:
    """Return the ``(start, end)`` of the minimal window of ``haystack``
    containing ``needle`` as an in-order subsequence, or ``None``.

    经典 O(len(haystack) × len(needle)) DP：逐位扫描 haystack，``dp[j]``
    维护"``needle[:j+1]`` 作为子序列匹配、末字符落在已扫描位的**最大起点**"——
    固定终点时起点越晚窗口越紧凑。``needle`` 末字符命中的每次补全即产生一个
    候选窗口 ``(dp[m-1], i)``，取跨度最小者。贪心最早匹配在 ``aXaXaXb`` 类
    形态下会给出非最小窗口（起点 0 而非 4），DP 保证子序列层排名可预期。
    """
    n, m = len(haystack), len(needle)
    if m == 0 or n < m:
        return None
    best: tuple[int, int] | None = None
    # dp[j] = 最大起点 s，使 needle[:j+1] 是 haystack[s..i] 的子序列；-1 = 尚未匹配
    dp = [-1] * m
    for i, ch in enumerate(haystack):
        # 降序遍历：同一位上 dp[j-1] 必须取自上一扫描位（prev），不能吃到位
        # 于同一位的低层更新（一个字符不能同时充当两个查询位的匹配）。
        for j in range(min(m - 1, i), -1, -1):
            if ch != needle[j]:
                continue
            if j == 0:
                dp[0] = i
            elif dp[j - 1] != -1:
                if dp[j - 1] > dp[j]:
                    dp[j] = dp[j - 1]
                if j == m - 1:
                    span = i - dp[j]
                    if best is None or span < best[0]:
                        best = (dp[j], i)
    return best
