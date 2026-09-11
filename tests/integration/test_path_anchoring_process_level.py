"""N4b 路径锚定进程级实证（Phase F F-2，ADR-035 反向实证）.

N4（test_cwd_change_process_level）锁定的是"显式相对 .env 随 CWD"的旧行为；
本用例补锚定后的反向实证——**陌生 CWD + 无显式 DATABASE_URL/LOG_DIRECTORY**，
默认库/日志必须落用户数据锚定目录（platformdirs，此处 monkeypatch 注入临时
锚点），而不是陌生 CWD；且不再产生"数据库路径随启动目录变化"警告。

不污染真实用户目录：子进程内 setattr settings 模块的锚点常量到 tmp_path。
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_foreign_cwd_without_explicit_config_anchors_to_user_data_dir(
    tmp_path: Path,
) -> None:
    """陌生 CWD + 无显式配置 → 库/日志落锚定目录；CWD 无库；无 CWD 警告。"""
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    anchor_data = tmp_path / "anchor-data"
    anchor_logs = tmp_path / "anchor-logs"

    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("DATABASE_URL", None)
    env.pop("LOG_DIRECTORY", None)
    probe_code = (
        "import sys; sys.path.insert(0, r'%s'); "
        "from pathlib import Path; "
        "import photo_archiver.infrastructure.config.settings as s; "
        "s.APP_DATA_DIR = Path(r'%s'); s.APP_LOG_DIR = Path(r'%s'); "
        "from photo_archiver.app import bootstrap_application; "
        "ctx = bootstrap_application(); "
        "print('DB_PATH::' + str(ctx.settings.database_path.resolve())); "
        "print('LOG_DIR::' + str(ctx.settings.log_directory.resolve()))"
        % (REPO_ROOT / "src", anchor_data, anchor_logs)
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

    expected_db = (anchor_data / "photo_archiver.db").resolve()
    assert (anchor_data / "photo_archiver.db").is_file(), result.stdout + result.stderr
    assert f"DB_PATH::{expected_db}" in result.stdout
    assert f"LOG_DIR::{anchor_logs.resolve()}" in result.stdout
    # 陌生 CWD 下不应出现任何库/日志文件（锚定生效的反向实证）
    assert not (foreign / "data" / "photo_archiver.db").exists()
    assert not (foreign / "logs").exists()

    # 锚定路径是绝对路径 → 无"随启动目录变化"警告
    log_files = list((anchor_logs).glob("*.log"))
    assert log_files, "bootstrap must write logs under the anchored dir"
    log_text = log_files[0].read_text(encoding="utf-8")
    assert "数据库路径随启动目录变化" not in log_text