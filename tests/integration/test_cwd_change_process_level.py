"""N4 换目录进程级实证（A3 后半自动化等价物）.

P0-9（D-B5）的风险本质是**进程级 CWD 依赖**：同一份相对路径 `.env`，从不同
目录启动会在彼处另建一套库/日志。单测矩阵（``test_cwd_dependent_path_warnings``）
已锁定警告函数与日志写入，本用例补进程级实证——在陌生 CWD 放一份相对路径
`.env`，以子进程真实启动 bootstrap：

- 相对 ``DATABASE_URL`` 解析到**陌生 CWD** 之下（那里真的建出库文件）；
- 日志警告"随启动目录变化"出现，且"本次解析为"指向陌生 CWD 下的绝对路径。

取代桌面清单 A3 后半的手工环节（该风险为日志证据，人工无需再核对）。
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_bootstrap_in_foreign_cwd_resolves_relative_paths_under_that_cwd(
    tmp_path: Path,
) -> None:
    """陌生 CWD + 相对 `.env`：库与日志都落在那边，警告指认新解析路径。"""
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / ".env").write_text(
        "DATABASE_URL=sqlite:///data/probe.db\nLOG_DIRECTORY=logs\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONIOENCODING"] = "utf-8"
    probe_code = (
        f"import sys; sys.path.insert(0, r'{REPO_ROOT / 'src'}'); "
        "from photo_archiver.app import bootstrap_application; "
        "ctx = bootstrap_application(); "
        "print('DB_PATH::' + str(ctx.settings.database_path.resolve()))"
    )

    result = subprocess.run(
        [sys.executable, "-c", probe_code],
        cwd=foreign,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr

    expected_db = (foreign / "data" / "probe.db").resolve()
    assert (foreign / "data" / "probe.db").is_file(), result.stdout + result.stderr
    assert f"DB_PATH::{expected_db}" in result.stdout

    log_files = list((foreign / "logs").glob("*.log"))
    assert log_files, "bootstrap must write the startup log under the foreign CWD"
    log_text = log_files[0].read_text(encoding="utf-8")
    assert "数据库路径随启动目录变化" in log_text
    assert str(expected_db) in log_text  # "本次解析为"指向陌生 CWD
