# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the PhotoArchiver Windows build (ADR-031 方案 B).

Build from the repository root::

    pyinstaller --noconfirm packaging/windows/photo_archiver.spec

onedir 形态（决策 D-P6）：启动快、杀软误报少。console=True 保留：CLI 子命令
（scan / recognize / export / …）与 GUI 共用一个可执行文件，控制台便于
诊断；P-2 安装器阶段再评估分离 windowed/cli 双产物。
"""

import os
import sys
from PyInstaller.utils.hooks import collect_all

# 相对路径在 spec 中的解析基准不可靠（script 相对 specdir、pathex 相对 CWD），
# 一律用 SPECPATH 推导绝对路径。
ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))


datas = []
binaries = []
hiddenimports = []

# insightface 1.0.1：sdist-only 包，含数据文件（模型注册 yaml 等）与延迟导入；
# PyInstaller 静态分析需要显式全量收集。
insightface_datas, insightface_binaries, insightface_hiddenimports = collect_all(
    "insightface"
)
datas += insightface_datas
binaries += insightface_binaries
hiddenimports += insightface_hiddenimports

# Alembic 迁移脚本：alembic.ini 置于 bundle 根、alembic/ 整目录随行——
# frozen 模式下 runner 从 sys._MEIPASS 解析（alembic_runner 冻结感知）。
datas += [
    (os.path.join(ROOT, "alembic.ini"), "."),
    (os.path.join(ROOT, "alembic", "env.py"), "alembic"),
    (os.path.join(ROOT, "alembic", "script.py.mako"), "alembic"),
]
for version_file in os.listdir(os.path.join(ROOT, "alembic", "versions")):
    if version_file.endswith(".py"):
        datas.append((
            os.path.join(ROOT, "alembic", "versions", version_file),
            "alembic/versions",
        ))

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT, os.path.join(ROOT, "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PhotoArchiver",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="PhotoArchiver",
)
