"""Stage F validation tool tests — pure calibration-stat helpers.

The tool script lives in ``tools/`` (not a package), so it is loaded via
``importlib`` from its file path (download_models.py precedent). Only the
pure statistics helpers are tested — no model, no database, no real photos.
"""

import importlib.util
from pathlib import Path

TOOL_PATH = Path(__file__).resolve().parents[3] / "tools" / "validate_stage_f.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location(
        "validate_stage_f_under_test", TOOL_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_percentile_is_nearest_rank_and_deterministic():
    tool = _load_tool()
    values = [0.5, 0.7, 0.9, 0.8, 0.6]
    assert tool.percentile(values, 50) == 0.7
    assert tool.percentile(values, 0) == 0.5
    assert tool.percentile(values, 100) == 0.9
    assert tool.percentile(values, 50) == tool.percentile(list(reversed(values)), 50)


def test_percentile_empty_returns_none():
    tool = _load_tool()
    assert tool.percentile([], 50) is None
    assert tool.percentile_table([]) == {f"p{t}": None for t in (10, 25, 50, 75, 90)}


def test_distribution_counts_and_sorts_by_value():
    tool = _load_tool()
    assert tool.distribution([3, 1, 3, 7]) == {"1": 1, "3": 2, "7": 1}
    keys = list(tool.distribution([10, 2, 2]).keys())
    assert keys == ["2", "10"]  # 值升序（字符串键，JSON 友好）


def test_cluster_size_buckets_cover_all_sizes():
    tool = _load_tool()
    buckets = tool.cluster_size_buckets([1, 2, 5, 6, 10, 11, 20, 21, 50, 51, 100])
    assert buckets == {"1": 1, "2-5": 2, "6-10": 2, "11-20": 2, "21-50": 2, "51+": 2}


def test_quality_bands_never_lose_observations():
    """分带必须覆盖全部观测（0 ≤ score ≤ 1），任何值都不丢失。"""
    tool = _load_tool()
    values = [0.0, 0.29, 0.30, 0.49, 0.50, 0.69, 0.70, 0.89, 0.90, 1.0]
    bands = tool.quality_bands(values)
    assert sum(bands.values()) == len(values)
    assert bands["<0.30"] == 2 and bands[">=0.90"] == 2
