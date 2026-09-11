# PhotoArchiver — 项目综合体检报告（Project Health Check）

> **文档性质**：独立、端到端、以当前 HEAD 为唯一基准的全项目体检
> **体检时间**：2026-09-10
> **基线**：HEAD `a03ce25`（== `origin/main`，working tree clean）
> **版本**：v2.4.0（tag `v2.4.0` = `93b7a15`）
> **方法**：Evidence Driven / Current HEAD Driven —— 所有结论基于当前源码 + 当前测试 + 当前正式文档交叉验证，**不以 2026-09-02 基线报告（`PROJECT_HEALTH_CHECK.md`，HEAD `3a2ef0a`）的结论为事实来源**，仅将其 18 项 Finding 作为"待复判清单"
> **历史基线**：`docs/health-check/PROJECT_HEALTH_CHECK.md`（2026-09-02，HEAD `3a2ef0a`）——保留为历史，勿删
> **配套**：`docs/roadmap/DEVELOPMENT_ROADMAP.md`（开发计划）｜`.ai/PROJECT_STATUS.md`（实时状态）

---

## 1. Executive Summary

**PROJECT HEALTH: GOOD（健康，可发布；有 6 项用户可达缺口待 owner 决策）**

相较 2026-09-02 基线，本轮是**实质性跃迁**：基线报告的 3 项 S1 级用户可见功能失效中，2 项已彻底修复（缩略图渲染、Excel 导入），第 3 项（插件 UI）从"死路径 bug"转为"机制在但生产不可达"的半修状态；数据安全底线（WAL + busy_timeout、启动备份、损坏库友好提示、模型摘要 fail-closed、导入事务化、扫描单飞守卫）**全部落地**；Phase E 库管理（删除登记 / 删除人员 / 重复处置 / 重扫对账 / prune-missing CLI）从"零 DELETE API"变为完整能力。四项质量门实测全绿，三平台 CI 绿。

**一句话结论**：这是一个工程质量扎实、可以真实使用的产品；剩余问题**均非崩溃性缺陷**，集中在三类——① 数据库路径 CWD 相对（macOS 发布阻塞）；② Windows 文件名/junction 语义未净化；③ 面向人类读者的 `README.md` 存在与现状直接矛盾的自述。

### 本轮新发现（最高优先级 3 项）

| # | 发现 | 级别 | 为什么重要 |
|---|---|---|---|
| **N-1** | `_add_plugin_actions()` 在**生产代码中零调用**，仅测试调用 | Important | 插件动作对真实用户**仍不可见**。旧基线的 P-1 死路径被"修复"成了"根本不调用"，用户视角未变；而 `README.md` 与 FAQ 仍宣传插件能力 |
| **N-2** | `README.md` "待实现"段（:270-285）**与现状直接矛盾**：把已完成并验证的 Step 14 Export、Step 15 Plugin System、Alembic 迁移体系列为"待实现"，同文件 :9/:252 又称"全部 15 步完成" | Important | README 是人类读者第一入口；自相矛盾 + 陈旧测试计数（:267 "226 passed / 8 skipped"，实际 713 收集）直接损害可信度 |
| **N-3** | 导入（import）任务仍**未接 cancelled 信号**；导出**无取消通道** | Minor/Important | 用户取消导入后 UI 停在 "Cancelling..." 不复位（旧 F-2 的剩余缺口） |

---

## 2. Current Baseline

### 2.1 Git

| 项 | 值 |
|---|---|
| Branch | `main` |
| HEAD | `a03ce25` |
| Origin | `origin/main` == 本地 HEAD，`up to date` |
| Working Tree | **Clean**（无已跟踪文件改动） |
| 未跟踪 | `.mypy_cache_run/`（工具缓存，非源码，建议加入 .gitignore 或删除） |
| 历史锚点 | `v2.4.0` → `93b7a15`；`v2.3.2` → `2aadcee`；`v2.3.1` → `90c46db`；`v2.3.0` → `e14409e` |

### 2.2 版本链（三处一致 ✅）

| 源 | 值 |
|---|---|
| `pyproject.toml:7` | `version = "2.4.0"` |
| `.env.example:8` | `APP_VERSION=2.4.0` |
| `CHANGELOG.md:9` | `## [2.4.0] - 2026-09-08` |

### 2.3 质量门（本轮实测）

| 门 | 命令 | 结果 | 耗时 |
|---|---|---|---|
| pytest | `pytest -q` | **710 passed / 3 skipped / 0 failed**（713 collected） | 151.97s |
| ruff | `ruff check .` | **All checks passed** | — |
| mypy | `mypy src` | **Success: no issues found in 189 source files** | 25s |
| pip check | `pip check` | **No broken requirements found** | — |

3 个 skipped 全部为 `tests/unit/application/test_archive_executor_symlink.py`（平台/账户不允许创建符号链接）→ **环境限制，非产品缺陷**，与 `.ai/PROJECT_STATUS.md` §5 基线 710/3/0 完全一致。

### 2.4 规模

| 指标 | 值 |
|---|---|
| 源码 | 189 文件 / **16,337 行** |
| 测试 | 116 文件 / **18,905 行**（测试:源码 = **1.16 : 1**） |
| 测试用例 | 713 collected（106 个测试模块） |
| 入库文件 | 375（**0 个 .pyc、0 个 .log、0 个密钥/凭证文件**） |

---

## 3. Architecture Health

**结论：分层架构实测合规，五项边界全清，无越界导入。**

| 边界 | 检查 | 结果 |
|---|---|---|
| Domain 零框架依赖 | 无 PySide6/numpy/pandas/openpyxl/sqlalchemy/PIL/cv2 导入 | ✅ |
| Presentation 不触 Infrastructure | 无 `from photo_archiver.infrastructure`、无 `import sqlite3` | ✅ |
| Application 无 GUI | 无 PySide6 导入 | ✅ |
| Workers 仅 QtCore | 无 QtWidgets/QtGui 导入（ADR-007、DEP-040） | ✅ |
| Infrastructure 不绕过 Application | 无直接构造 UseCase / 反向依赖 | ✅ |

**ADR 状态**：最新为 **ADR-034**（Phase E 删除语义与库管理，Accepted，D1–D6 全部按 owner 裁决执行）。**无"已批准但未完成"的架构决策**——ADR-034 的影响范围（协议扩 remove、双仓储实现、四个删除/对账服务、UI 入口、prune-missing CLI、update_metadata）已全部落地并经测试锁定。

**关键不变量**：删除操作磁盘文件零触碰（D3），由 `ADR-034` 强制；`PRAGMA foreign_keys=ON` 保证级联语义真实生效。

---

## 4. Product Completeness

### 4.1 历史 S1 级失效复判（旧基线 §4.2）

| 旧编号 | 问题 | 本次判定 | 证据 |
|---|---|---|---|
| P-1 | 插件系统在 UI 中从未加载 | **PARTIAL** | 错路径 bug 已修（`main_window.py:255` 只构造 `PluginRegistry`）；但 `_add_plugin_actions()` **生产零调用**（仅 `test_plugin_ui_loading.py:69` 调用）→ 用户仍看不到插件动作 |
| P-2 | 缩略图从不渲染 | **FIXED** | `main_window.py:355` 装 `PhotoThumbnailDelegate` → `photo_list_delegate.py:47` 消费 `THUMBNAIL_ROLE` ← `photo_list_model.py:73-74` 填充该 role，**端到端闭环成立** |
| P-3 | Excel 人员导入断线 | **FIXED** | `app/services.py:183` 装配 `DispatchingPersonImportReader`；`dispatching_person_import_reader.py:21,53` 按 `.xlsx/.xlsm` 路由；`main_window.py:524` + `ui_text.py:48` 过滤器含 `.xlsx` |

### 4.2 有意缺口（Deferred / Blocked，非缺陷）

| 项 | 状态 | 说明 |
|---|---|---|
| `ExportScope.CURRENT_BATCH` | **DEFERRED（契约既定）** | `export_service.py:122-124` 显式 `ValueError`，注明 FEATURE-004 §2/D4——无批次持久化。UI 已禁用 radio，属诚实拒绝 |
| 安装态分发 | **BY-DESIGN** | ADR-031：受支持形态 = clone + venv + `python main.py`；Release 的 wheel/sdist 为源码元数据产物 |
| i18n 实装 | **Out-of-Scope** | roadmap §13.7 明示不做 |
| 批次持久化 | **owner 门控** | roadmap §13.12 明示 AI 不得自行实施 |

---

## 5. Core Workflow Health

**结论：10 环节中 9 个为真实闭环；唯一 PARTIAL 为并行匹配的崩溃持久化窗口。**

| 环节 | 判定 | 关键证据 |
|---|---|---|
| 1. Import People | **CLOSED LOOP** | 已按批 500 UoW 提交（`import_people_service.py:87-88`）；NULL identity 行经 `find_by_name_department` 去重（:130-132）——旧 F-4 已修 |
| 2. Scan Photos | **CLOSED LOOP** | 单 UoW + 逐照片异常隔离；**新增单飞守卫**（`scan_controller.py:53-55`）；**新增内容变更对账**（hash 强比对 / mtime+size 弱退化 → `update_metadata`）；`prune-missing` CLI 处理失联（dry-run 默认） |
| 3. Metadata | **CLOSED LOOP** | EXIF → mtime → None 三级回退；子 IFD 拍摄时刻修复（ISSUE-019 已关闭） |
| 4. Thumbnail | **CLOSED LOOP** | 生成 + 缓存 + 异步加载 + **渲染闭环已通**（P-2 修复） |
| 5. Recognition + Matching | **CLOSED LOOP（附条件）** | 顺序路径逐张 `add`（:147）；**并行路径仍末尾单次 `add_many`（:242）→ 进程崩溃丢整批**（旧 F-8 剩余，默认 `max_workers=1` 规避） |
| 6. Review | **CLOSED LOOP** | 逐条 UoW + 终态幂等跳过 |
| 7. Filter / Search | **CLOSED LOOP（小缺口）** | 三轴 AND 语义全通；**JOIN 无 DISTINCT**（`sqlite_photo_repository.py:195-198`）→ 多识别行照片重复出现；"未匹配"哨兵仅 docstring 承诺未实现（`photo_search_criteria.py:38-39`） |
| 8. Archive | **CLOSED LOOP** | Planner→Plan→Executor；dry-run；skip/overwrite/rename；包容校验 |
| 9. Export | **CLOSED LOOP** | ALL/FILTERED 全链闭环；**原子写已实现**（`_atomic_write.py:8-23` temp + `os.replace`）——旧 F-16 已修；公式注入防护在位。剩余：全内存收集无流式（当前规模可接受） |
| 10. Duplicate Detection | **CLOSED LOOP（已升级）** | 单 SQL push-down；**Phase E D6 新增"按建议处置"**（保留最早注册一张） |

**Phase E 增量（v2.4.0 新增，全部经测试锁定）**：删除照片（D1/D3）、删除人员（D2/D3）、重复处置（D6）、重扫对账（D5）、prune-missing CLI（D5）——全部走确认流 + loguru 审计 + 启动备份兜底，磁盘文件零触碰。

---

## 6. UI / UX Health

| 项 | 现状 | 评价 |
|---|---|---|
| 主窗口 | 单 QToolBar + 9 QAction，无菜单栏 | 简洁够用 |
| 破坏性操作确认 | 归档预览 + **删除确认（级联计数预览）** + 重复处置确认 | ✅ 良好（Phase E 强化） |
| 缩略图渲染 | **已闭环** | ✅（旧 P-2 已修） |
| 插件动作可见性 | **不可见**——`_add_plugin_actions()` 生产零调用 | ❌ 见 N-1 |
| 语言下拉 | 已持久化但**无运行时效果**（`translations.py:44-66` 写死 zh_CN） | ⚠️ 占位控件（旧 F-15 未修） |
| 导入取消 | 无 cancelled 接线 → 取消后 UI 停 "Cancelling..." | ⚠️ 见 N-3 |
| 导出取消 | 无取消通道（Cancel 按钮导出期间无效） | ⚠️ |
| 空态 / 识别状态列 | 照片列表无识别/归档状态列；无空态占位 | 需补 |
| 术语一致性 | 中文注释 + 英文 UI 文案统一；review 行裸 UUID 可读性差 | Minor |

---

## 7. Database / Persistence

**结论：Schema 健康、WAL + busy_timeout 在位、启动备份兜底、损坏库友好提示；最大遗留是库路径 CWD 相对。**

### 7.1 Schema

6 表（ADR-027，Alembic `001_initial_v4` + `002_split_create_ddl` 唯一权威）：people（identity UNIQUE）/ folders / photos（folder_id **SET NULL**）/ recognition_results（photo_id **CASCADE**, person_id **SET NULL**）/ person_embeddings（person_id **CASCADE**）/ archive_records（photo_id **CASCADE**）。`PRAGMA foreign_keys=ON` 每连接强制执行 —— Phase E 的删除级联正是建立在这套既有语义上（ADR-034 D1/D2 确认而非新设计，零 schema migration）。

### 7.2 复判结果

| 旧编号 | 项 | 判定 | 证据 |
|---|---|---|---|
| D-1 / F-5 | WAL + busy_timeout | **FIXED** | `sqlite_connection.py:18-29` 每连接设 `busy_timeout=5000` + `journal_mode=WAL` |
| D-2 / F-6 | 备份与损坏处理 | **FIXED（GUI）** | `backup.py` 用 `VACUUM INTO`；GUI 启动备份（`main.py:250`）；`CorruptedDatabaseError` 友好提示（`main.py:29,244`）。**缺口：CLI 启动无备份快照** |
| D-3 / F-7 | 库路径 CWD 相对 | **OPEN** | `settings.py:19` 默认仍 `sqlite:///data/photo_archiver.db`；`.env` 按 CWD 加载（:47）；仅 `bootstrap.py:95` 警告，**未锚定绝对路径** → 换目录启动静默换库（macOS Finder 双启 CWD=`/` 必触发） |
| D-4 | `user_version=4` 死状态 | Observation | 仍为死状态，无 reader；无害 |
| D-5 / F-13 | 大小写重复 + JOIN 无 DISTINCT | **OPEN** | 路径精确比较 + UNIQUE 大小写敏感；`search()` 无 DISTINCT |
| D-7 | 归档 FS 复制在 UoW 窗口内 | Minor | 崩溃时 DB 回滚而文件已落盘，靠 skip 策略收敛 |

---

## 8. Dependency Health

**结论：清单治理良好，无未声明导入，无版本冲突；摩擦点是 insightface 源码编译。**

| 项 | 事实 |
|---|---|
| 清单体系 | `base.txt` / `dev.txt` / `lock.txt` / `ai.txt`（扩展挂载点）+ README 策略文档 ✅ |
| 未声明导入 | **零** —— src 与 main.py 的第三方导入全部在 base.txt 内 ✅ |
| 批准未使用 | `pandas 2.3.1`、`watchdog 6.0.0` —— base.txt 注释明示 "approved but unused, zero import"，有据可查非泄漏；roadmap §13.5 明示不移除 |
| 锁定 | `lock.txt` 含 `python-discovery==1.4.4`（非常见包），建议下次 freeze 复核 |
| **insightface 1.0.1** | **sdist-only：每个用户安装都本地编译 C++**（Windows 需 MSVC Build Tools；macOS 需 Xcode CLT）——目标非技术受众安装的第一大障碍 |
| onnxruntime 1.27.0 | CPU-only；CUDA provider 警告为良性回退（pytest warnings 实测），无 GPU 路径 |
| **覆盖率工具** | **缺失** —— dev.txt 无 pytest-cov，venv 无 coverage 模块，**全仓无覆盖率度量** |

---

## 9. Worker / Concurrency

| 旧编号 | 项 | 判定 | 证据 |
|---|---|---|---|
| W-1 | 异常纪律 | ✅ 维持 | WorkerTask 捕获 → TaskFailed → UI 弹窗 |
| W-2 / F-2 | cancelled 信号接线 | **PARTIAL** | **scan 已接**（`main_window.py:501,515-520`）；**import 未接**（`import_people_controller.py:51` 无 cancelled 参数）；export 无取消通道（`main_window.py:784-786`） |
| W-3 / F-3 | Scan 单飞防护 | **FIXED** | `scan_controller.py:53-55` 守卫，产品代码由 `test_scan_single_flight.py:67` 锁定 |
| W-4 | 取消仅批边界 | Known Limitation（LIMIT-002） | 设计特征，非缺陷 |
| W-5 / F-14 | autoDelete 悬引用 | **FIXED** | terminal releaser 释放 `_active_runnable`（`scan_controller.py:88-102`）。**残留**：`main_window.py:493,733` 的 `_active_runnable` 终态未清零（Observation） |
| W-6 | UI 线程同步操作 | Minor | review 转换 / 筛选 / 重复检测 / 归档 planner N+1 在 UI 线程（by-design，当前规模可接受） |
| W-7 | 线程预算 | Observation | QtWorkerExecutor 未传 max_workers；match 内层再开 ThreadPoolExecutor（两级并发） |
| F-17 | app↔presentation 循环 import | **NOT REPRODUCED** | 无硬环；规避注释见 `presentation/views/__init__.py:3` |
| F-11 | junction 环路递归 | **OPEN** | `local_photo_file_scanner.py:27-32` 用 `glob("**/*")`，无 is_symlink / 深度上限 / 已访问集合防护（Python 3.11 pathlib 不识别 Windows junction） |

---

## 10. Testing / Quality

**结论：规模与真实度俱佳，四门全绿、零 flake；短板在覆盖率缺位与部分结构性缺口。**

### 10.1 套件盘点

- 106 个测试模块，713 用例，18,905 行测试代码（**测试:源码 = 1.16:1**，比例优秀）
- 测试全部使用**文件级真实 SQLite**（零 `:memory:`）；pytest-qt 4.5.0 驱动 UI 测试
- 真实链路 E2E 文化：UI → Controller → QtWorkerExecutor → Task → Service → Repository → SQLite → 文件系统

### 10.2 本轮执行

**710 passed / 3 skipped / 0 failed**（151.97s）。**零 flake**——旧基线的 F-002（match 控制器时序 flake，曾升级为 IMPORTANT）本轮不复现，判定 **RESOLVED**。

### 10.3 结构性缺口

| # | 缺口 | 影响 |
|---|---|---|
| T-1 | 无 import-linter / 自动化分层断言 | 分层回归靠人工 + mypy |
| T-2 | **无覆盖率工具**（pytest-cov / coverage 均未安装） | 无法量化盲区——本轮体检**无法给出覆盖率数字** |
| T-3 | 对话框直测仍偏少 | — |
| T-5 | CI "no SKIPPED" 守卫用 `pytest --co -q`（收集期不含运行时 importorskip） | 守卫效力存疑 |
| T-6 | Qt 原生级崩溃（exit 127）在特定子集顺序可复现（LIMIT-004） | 环境依赖型，全量顺序安全 |

### 10.4 CI（三平台）

`ci.yml`：ubuntu / windows / macos × py3.11 矩阵，`fail-fast: false`，`QT_QPA_PLATFORM=offscreen`。
防护链完整：模型缓存 → 3 次重试下载 → **模型包非空断言（R-4）** → ruff → mypy → pytest → **AI 集成测试 no-skip 断言** → **UI 测试 no-skip 断言**。
✅ 相比旧基线，模型摘要已钉定且 fail-closed，CI 不再传 `--allow-unverified`（旧 F-9 已修）。

---

## 11. Security

**结论：防护成体系且多数经测试锁定；模型完整性已从 fail-open 转为 fail-closed。**

| 域 | 状态 | 证据 / 缺口 |
|---|---|---|
| 路径穿越 | ✅ 强 | ArchivePath VO 拒空段 / `/` `\` `.` `..`；executor 双重包容校验；拒绝 symlink 叶目标 |
| **Windows 文件名语义** | ❌ **OPEN** | `archive_path.py:39-74` 仅 strip + 拒分隔符 + `..`；**未净化保留设备名（CON/PRN/AUX/NUL/COM1-9/LPT1-9）、尾点尾空格、非法字符 `: * ? " < > \|`** → 人名 `con` 或文件 `nul.jpg` 会使归档项系统性 FAILED（被逐项 OSError 隔离兜底，但持续失败） |
| Symlink / Junction | ⚠️ 半覆盖 | 归档侧强；**扫描侧无 junction 防护**（F-11，见 §9） |
| 图像解压 | ✅ | MAX_IMAGE_PIXELS 由 settings 强制；DecompressionBomb 双路径映射隔离；缩略图剥离 EXIF（隐私） |
| 公式注入 | ✅（小缺口） | CSV/Excel 每格 `'` 前缀（`= + @ \t \r` 及非数字 `-`）；HTML 全转义；OWASP 亦列的前导 `\|` 未中和 |
| SQL 注入 | ✅ | 全参数化；f-string 仅用于 `PRAGMA` 常量（`sqlite_connection.py:27-29`），无用户输入拼接 |
| **模型完整性** | ✅ **FIXED** | `download_models.py:54-60` buffalo_l 摘要已钉；:110-125 **未钉摘要且未显式放行时拒绝解包（fail-closed）**；CI 不再传 `--allow-unverified`（旧 F-9 已修）。**残留**：`antelopev2` 摘要仍为空串（:60），fail-closed 下无安全风险，属技术债 |
| 配置校验 | ✅ | pydantic-settings 全字段校验（sqlite-only URL、worker 边界、阈值、像素下限、冲突策略枚举） |
| 仓库卫生 | ✅ | 0 个密钥/凭证文件入库；0 个 .log 入库；0 个 .pyc 入库 |
| 代码风险面 | ✅ | 无 `eval` / `exec` / `os.system` / `shell=True` / `pickle.loads`；无 bare except；无 `print()` / TODO / FIXME |
| 导出原子性 | ✅ **FIXED** | `_atomic_write.py:8-23` temp + `os.replace` |

---

## 12. Performance

| 项 | 事实 | 评价 |
|---|---|---|
| 人脸识别 | ADR-032/033：2600 张串行 656.9s → 332.0s（1.98×）；4-worker 11.22 photos/s（2.22×） | ✅ 已达标，W2-3=A 有意收尾 |
| 插件查询 | ADR-029：18.2×（N+1 → 批量联查） | ✅ |
| 搜索联查 | ADR-029 延伸（`search_photos` 批量联查） | ✅ |
| 大批量扫描 | 单 UoW 含逐张 SHA-256；WAL + busy_timeout 已缓解写锁竞争 | ✅ 风险已降级 |
| 导出 | 全内存收集 + openpyxl 整簿，无流式（**原子写已补**） | ⚠️ 数万行+ 内存受限；当前规模可接受 |
| 归档 preview | Planner N+1 仓储读在 UI 线程 | ⚠️ 大目录可感 |
| 缩略图 | 异步 + 去重 + 内容寻址缓存；**孤儿缓存无清理**（`thumbnail_cache.py:7-54` 无 cleanup） | ⚠️ 长期运行缓慢增长 |
| 基准工具 | `tools/bench_recognition.py` / `bench_plugin_search.py` 可复跑 | ✅ 性能治理有证据链 |

---

## 13. Cross-platform Readiness

| 维度 | Windows | macOS |
|---|---|---|
| 源码/clone 运行 | ✅ 实测（本轮体检环境即 Windows） | ✅ CI 绿灯背书（同套件） |
| 三平台 CI | ✅ ubuntu / windows / macos × py3.11 全绿 | ✅ 同左 |
| 路径处理 | ✅ pathlib 全面，无硬编码盘符/反斜杠 | ✅ |
| 数据库位置 | ⚠️ CWD 相对 | ❌ **Finder 双启 CWD=`/` 必换库**（F-7 未修） |
| 安装摩擦 | ❌ insightface 需 MSVC C++ 编译 | ❌ insightface 需 Xcode CLT 编译 |
| 保留文件名 / junction | ❌ 未净化保留名；junction 环路递归风险 | n/a |
| App 打包 | 无（ADR-031 source-only） | 无 .app bundle |
| macOS CI 稳定性 | n/a | ⚠️ LIMIT-006：真实执行器压力扫描段错误（SIGSEGV），4 个用例 darwin skip |

**判定**：准确表述为 **三平台测试矩阵绿 + Windows 源码形态实测可用；macOS 有 CI 背书但无长期使用态证据，且受 CWD 库路径（F-7）与编译安装双重制约**。仍不得声称"跨平台完成"。

---

## 14. Release Readiness

| 发布要素 | 状态 | 说明 |
|---|---|---|
| 受支持运行形态 | ✅ | clone + venv + `pip install -r requirements/base.txt` + `python main.py`（ADR-031） |
| wheel/sdist | ⚠️ | 按裁决为"源码元数据产物"；包内无依赖声明/入口，`pyproject.toml` 无 `dependencies` |
| Installer / 打包 | ❌ | 无 PyInstaller/MSI/NSIS/.app；ADR-031 方案 B 未触发 |
| 首启体验 | ⚠️ | .env 非必需 ✓；但模型包手动下载（300MB）+ insightface 编译 + ARCHIVE_ROOT 手配 |
| 数据库初始化/迁移 | ✅ | 首启自动建库 + Alembic upgrade head；损坏库有友好提示（已修） |
| 错误恢复 | ✅/⚠️ | 任务级优秀；库级有启动备份（GUI）。**CLI 无备份** |
| 日志 | ✅ | loguru + 轮转（10MB）+ LOG_DIRECTORY 可配 |
| 文档 | ⚠️ | user-guide 链路准确；**README 有自相矛盾与陈旧计数（N-2）** |
| 版本链 | ✅ | 2.4.0 三处一致 |

**发布准备度分级**：

- **Development Ready：✅ 已达到**
- **Beta Ready：✅ 已达到**（技术用户 + Windows 优先；较基线提升——三项 S1 失效已修 2 项，数据安全底线已立）
- **Release Candidate：⚠️ 接近**——差：库路径绝对锚定（F-7）、Windows 文件名净化（F-10）、插件动作可见性（N-1）、README 修订（N-2）
- **Production Ready：❌**——再加：分发形态（方案 B / installer）、首启体验、对非技术用户的支撑链

**v2.4.0 收官**：CI 三平台绿，tag 已打，Release 已由 tag 触发生成。**唯一阻塞 = owner 手工两步**（核对 Release 资产 + 粘贴 `CHANGELOG.md` 第 9–54 行进 body 后签核）。

---

## 15. Findings Register（本轮全量）

### 15.1 旧基线 18 项 Finding 复判

| 旧编号 | 项 | 本次判定 |
|---|---|---|
| F-1a | 插件 UI 死路径 | **PARTIAL** → 见 N-1 |
| F-1b | 缩略图不渲染 | **FIXED** ✅ |
| F-1c | Excel 导入断线 | **FIXED** ✅ |
| F-2 | scan/import cancelled 未接线 | **PARTIAL** → 见 N-3 |
| F-3 | Scan 无单飞防护 | **FIXED** ✅ |
| F-4 | 导入无事务 + 重复入库 | **FIXED** ✅ |
| F-5 | 无 WAL / busy_timeout | **FIXED** ✅ |
| F-6 | 零备份 + 损坏库崩溃 | **FIXED（GUI）** / CLI 缺口 → N-4 |
| F-7 | DB/模型/.env 路径 CWD 相对 | **OPEN** ⚠️ |
| F-8 | 并行匹配整批末次持久化 | **PARTIAL** ⚠️ |
| F-9 | 模型摘要 fail-open | **FIXED** ✅（fail-closed） |
| F-10 | Windows 保留名未净化 | **OPEN** ⚠️ |
| F-11 | junction 环路递归 | **OPEN** ⚠️ |
| F-12 | PROJECT_STATUS 漂移 | **FIXED** ✅（但 README 漂移为新形态 → N-2） |
| F-13 | search 无 DISTINCT / 无未匹配哨兵 | **OPEN** ⚠️ |
| F-14 | QRunnable autoDelete 悬引用 | **FIXED** ✅ |
| F-15 | 语言占位控件 | **OPEN** ⚠️ |
| F-16 | 导出无原子写 | **FIXED** ✅ |
| F-17 | app↔presentation 循环 import | **NOT REPRODUCED** |
| F-18 | 杂项（孤儿缓存等） | **OPEN（缩略图孤儿缓存）** ⚠️ |

**统计：FIXED 10 · PARTIAL 2 · OPEN 6 · NOT REPRODUCED 1**（旧 F-12 视为已修，README 新漂移另计为 N-2）
另：旧 **F-002（审计级 flake）本轮零复现 → RESOLVED**。

### 15.2 本轮新发现

| # | 发现 | 级别 | 证据 | 建议 |
|---|---|---|---|---|
| **N-1** | `_add_plugin_actions()` 生产代码零调用，插件动作对用户不可见 | **Important** | `main_window.py:268` 定义，**仅** `test_plugin_ui_loading.py:69` 调用 | 二选一：① 接一个可配置插件目录并调用（恢复对外承诺）；② 明确将插件降级为"开发者扩展点"并同步修订 README/FAQ 宣传 |
| **N-2** | `README.md` "待实现"段与现状直接矛盾 + 陈旧测试计数（226 passed/8 skipped，实为 713 collected）+ 重复行 | **Important** | `README.md:270-285`、`:267`、`:264-265`；矛盾于 `:9`/`:252` | 删除"待实现"段；计数改为指针化引用 `.ai/PROJECT_STATUS.md` |
| **N-3** | import 任务无 cancelled 接线；export 无取消通道 | Minor→Important | `import_people_controller.py:51`；`main_window.py:784-786` | 补齐 cancelled 信号与终态复位 |
| **N-4** | CLI 启动无备份快照（GUI 有） | Minor | `main.py:38-49` `_bootstrap_for_cli` 未调用 `backup_database` | 与 GUI 对齐 |
| **N-5** | 导入去重按 name+department，会把同名同部门但不同 identity 的两名真实人员误判为重复而跳过 | Minor | `import_people_service.py:130` | 去重键增加 identity 参与判定 |
| **N-6** | `.xlsm` 读取器支持但文件选择器未列该扩展名 | Info | `ui_text.py:48` vs `dispatching_person_import_reader.py:21` | 过滤器补 `.xlsm` |
| **N-7** | `antelopev2` 模型摘要仍为空串 | Info（技术债） | `download_models.py:60`（fail-closed 下无安全风险） | 补钉摘要 |
| **N-8** | 缩略图孤儿缓存无清理 | Minor | `thumbnail_cache.py:7-54` 无 cleanup | 启动/退出时按内容寻址清理 |
| **N-9** | `main_window._active_runnable` 终态未清零 | Observation | `main_window.py:493,733` | 与 scan_controller 的 releaser 对齐 |

---

## 16. Feature Inventory（v2.4.0）

| ID | Feature | Status | User Value | Release Impact |
|---|---|---|---|---|
| FEAT-01 | 人员导入（txt/csv） | **COMPLETE** | 高 | 非阻塞 |
| FEAT-02 | 人员导入（Excel） | **COMPLETE**（P-3 已修） | 高 | 非阻塞 |
| FEAT-03 | 目录扫描/注册 + 重扫对账 | **COMPLETE**（Phase E D5 增强） | 高 | 非阻塞 |
| FEAT-04 | EXIF 元数据 | **COMPLETE** | 高 | 非阻塞 |
| FEAT-05 | 缩略图（生成+渲染） | **COMPLETE**（P-2 已修） | 高 | 非阻塞 |
| FEAT-06 | 人脸检测/识别/匹配 | **COMPLETE** | 高 | 非阻塞（并行崩溃丢批 F-8） |
| FEAT-07 | 识别审核 | **COMPLETE** | 高 | 非阻塞 |
| FEAT-08 | 筛选（status/person/date） | **COMPLETE** | 高 | 非阻塞（DISTINCT 缺口） |
| FEAT-09 | 归档 | **COMPLETE** | 高 | 非阻塞（Windows 保留名 F-10） |
| FEAT-10 | 导出 ALL/FILTERED | **COMPLETE**（原子写已补） | 高 | 非阻塞 |
| FEAT-11 | CURRENT_BATCH 导出 | **DEFERRED**（契约既定） | 低 | 非必需 |
| FEAT-12 | 重复图片检测 + 处置 | **COMPLETE**（Phase E D6 增强） | 中 | 非阻塞 |
| FEAT-13 | 插件系统 | **PARTIAL**（机制全，UI 不可达 N-1） | 中 | **对外承诺待澄清** |
| FEAT-14 | 设置 | PARTIAL（ARCHIVE_ROOT 无 UI；语言占位 F-15） | 中 | 非阻塞 |
| FEAT-15 | CLI（scan/archive/backfill/prune-missing） | **PARTIAL** | 中 | P1 增强（缺 import/export/recognize） |
| FEAT-16 | 持久化（Alembic + WAL + 备份） | **COMPLETE** | 高 | 非阻塞（CWD 路径 F-7） |
| FEAT-17 | 照片/人员删除、库对账 | **COMPLETE**（Phase E，旧"MISSING"已补） | 中 | 非阻塞 |
| FEAT-18 | 安装态分发 | **BLOCKED**（ADR-031 by-design） | 高 | v1.0 交付决策点 |
| FEAT-19 | 日志/配置体系 | **COMPLETE** | 中 | 非阻塞 |
| FEAT-20 | i18n | **PLACEHOLDER** | 低 | 已明示 Out-of-Scope |

---

## 17. Maturity Score

| 维度 | 得分 | 依据摘要 |
|---|---|---|
| 架构与分层 | **9 / 10** | 五项边界全清、ADR 体系完备、无越界 |
| 代码质量 | **9 / 10** | 四门全绿（ruff 0 / mypy 189 files 0 / pytest 710-0 / pip check 0）；无 print/TODO/bare except |
| 测试与 CI | **8.5 / 10** | 713 用例、测试:源码 1.16:1、三平台 CI + 多重守卫；扣分项：无覆盖率度量、无自动化分层断言 |
| 数据安全 | **8 / 10** | WAL + busy_timeout + 启动备份 + 损坏友好提示 + fail-closed 模型校验；扣分项：CWD 路径未锚定、CLI 无备份 |
| 安全 | **8 / 10** | 路径穿越/注入/解压炸弹防护成体系；扣分项：Windows 保留名未净化、junction 无防护 |
| 产品完整度 | **8.5 / 10** | 10 环节 9 闭环；Phase E 补齐删除与对账；扣分项：插件 UI 不可达、CURRENT_BATCH deferred |
| 文档一致性 | **6.5 / 10** | `.ai/` 四文档实时准确；扣分项：**README 自相矛盾 + 陈旧计数（N-2）** |
| 发布就绪 | **7.5 / 10** | v2.4.0 已发布待签核；扣分项：无 installer、首启摩擦（模型 300MB + insightface 编译） |
| 跨平台 | **7 / 10** | 三平台 CI 绿 + Windows 实测；扣分项：macOS CWD 库路径、无使用态证据 |

**综合成熟度：约 8.0 / 10**（较 2026-09-02 基线显著提升）

---

## 18. Completion Estimate

| 口径 | 估计 | 说明 |
|---|---|---|
| **Audit（工程质量）** | **97%** | 四门全绿、零 flake、边界合规、CI 三平台；余量在无覆盖率度量与自动化分层断言 |
| **Product（功能完整）** | **90%** | 核心 10 环节 9 闭环；Phase E 补齐删除/对账；余量在插件 UI（N-1）、CURRENT_BATCH、CLI 覆盖面 |
| **Release（面向目标受众可交付）** | **62%** | 提升项：数据安全底线已立、三项 S1 失效已修 2 项；仍缺：库路径锚定（F-7）、Windows 文件名净化（F-10）、分发形态、首启体验 |

### 「如果今天停止开发，PhotoArchiver 处于什么状态？」

**一个工程质量扎实、Windows 源码形态下可真实使用的照片归档工具**——扫描 → 元数据 → 识别 → 审核 → 归档 → 导出全链闭环，库管理能力（v2.4.0）齐备，数据安全有备份兜底，三平台 CI 绿。技术用户按 user-guide 即可上手。

**但**：① 非技术用户会被 insightface 编译 + 300MB 模型下载挡在门外；② macOS 用户换目录启动会静默换库；③ README 的自相矛盾会削弱第一印象；④ 插件能力对外宣称但用户实际看不到。

---

## 19. Gap Matrix（按优先级）

| 优先级 | 项 | 编号 | 类别 | 影响 |
|---|---|---|---|---|
| **P0-1** | 库路径绝对锚定（用户目录/注册表定位） | F-7 | 数据安全 | macOS 发布阻塞；换目录静默换库 |
| **P0-2** | Windows 保留名 / 非法字符净化 | F-10 | 正确性 | 人名 `con`、文件 `nul.jpg` 致归档持续失败 |
| **P1-1** | 插件动作可见性澄清 | N-1 | 对外承诺 | 要么接上，要么收回宣称 |
| **P1-2** | README 修订（删除矛盾"待实现"段 + 计数指针化） | N-2 | 文档 | 人类第一入口可信度 |
| **P1-3** | 导入 cancelled 接线 + 导出取消通道 | N-3 | UX | 取消后 UI 不复位 |
| **P1-4** | junction 环路防护 | F-11 | 健壮性 | Windows 递归失控 |
| **P1-5** | search DISTINCT + "未匹配"哨兵 | F-13 | 正确性 | 重复行；docstring 承诺未兑现 |
| **P2-1** | CLI 补齐（import/export/recognize） | — | 能力 | 自动化与批量运维 |
| **P2-2** | CLI 启动备份对齐 GUI | N-4 | 数据安全 | 一致性 |
| **P2-3** | 缩略图孤儿缓存清理 | N-8 | 资源 | 长期增长 |
| **P2-4** | 覆盖率度量引入 | T-2 | 质量可见性 | 无法量化盲区 |
| **P2-5** | 导入去重键修正 | N-5 | 正确性 | 同名同部门误判 |
| **P3** | 语言占位移除或实装 | F-15 | UX | 明示 Out-of-Scope 或实现 |
| **P3** | `.xlsm` 过滤器、antelopev2 摘要、_active_runnable 清零 | N-6/7/9 | 技术债 | 低 |

---

## 20. Risks

| 风险 | 级别 | 说明 | 缓解 |
|---|---|---|---|
| macOS 库路径 CWD 相对 | **High** | Finder 启动 CWD=`/` → 静默创建/使用另一个空库，用户会认为"数据丢了" | 已有启动警告；根治需 P0-1 |
| insightface 源码编译 | **High** | 每个用户安装都要本地编译 C++，非技术受众第一障碍 | 无（生态限制）；建议文档前置警示 |
| 插件能力名实不符 | Medium | 对外宣称 vs 用户不可见 | P1-1 澄清 |
| 并行匹配崩溃丢批 | Medium | `max_workers>1` 时末尾单次 add_many | 默认 `max_workers=1` 已规避；文档说明 |
| macOS 压力扫描段错误 | Low | LIMIT-006，4 用例 darwin skip | 已 skip；非产品代码因果 |
| Windows 子集顺序 Qt 崩溃 | Low | LIMIT-004，仅本地调试子集触发 | 全量顺序安全 |
| 覆盖率盲区 | Low | 无度量工具，盲区不可知 | 引入 pytest-cov（P2-4） |

---

## 21. Final Assessment

**PROJECT HEALTH: GOOD**

v2.4.0 是一个**可以真实交付使用**的版本。与 2026-09-02 基线相比，项目完成了一次从"工程质量好但产品有失效"到"工程质量好且产品可用"的跃迁：三项 S1 用户可见失效已修 2 项，第 3 项转化为待澄清的对外承诺问题；数据安全底线（WAL、备份、损坏提示、模型 fail-closed）全面落地；Phase E 让库从"只增不减"变为可运营。

**当前没有任何崩溃性或数据丢失性缺陷阻塞日常使用**。剩余 6 项 OPEN 全部是"边界场景 + 特定平台 + 名实不符"性质，可按 P0→P3 顺序排期，不影响 v2.4.0 签核。

**建议下一步（按 owner 决策）**：

1. **立即（非开发）**：完成 v2.4.0 Release 签核（粘贴 CHANGELOG 第 9–54 行进 body）
2. **P0**：库路径绝对锚定（F-7）+ Windows 文件名净化（F-10）
3. **P1**：插件动作澄清（N-1）+ README 修订（N-2）+ 导入取消接线（N-3）
4. **P2**：覆盖率度量引入 + CLI 补齐 + 杂项技术债

> ⚠️ 本轮新发现（N-1 ~ N-9）**未登记进 `.ai/KNOWN_ISSUES.md`** —— 该操作会改变项目"零未决问题"状态并影响 Release 签核口径，建议 owner 看过本报告后决策，由后续开发轮按 `.ai/rules/ai-rules.md` 统一登记。

---

## 附录 A — 本轮体检执行记录

| 项 | 命令 / 手段 | 结果 |
|---|---|---|
| Git 基线 | `git status` / `log` / `rev-parse` / `branch -vv` | main @ a03ce25，clean，== origin/main |
| 质量门 | `pytest -q` / `ruff check .` / `mypy src` / `pip check` | 710-3-0 / pass / 189 files 0 / pass |
| 分层边界 | 跨层导入 grep（Domain/Presentation/Application/Workers/Infrastructure） | 五项全清 |
| 依赖审计 | requirements 清单 vs 实际顶层导入比对 | 零未声明导入；pandas/watchdog 备注在案 |
| 安全扫描 | 危险调用 / SQL 拼接 / print / TODO / bare except / 密钥入库 | 全部为零 |
| 仓库卫生 | `git ls-files` 过滤 .pyc / .log / 敏感文件 | 0 / 0 / 0（375 入库文件） |
| CI 审查 | `.github/workflows/ci.yml` + `release.yml` | 三平台矩阵 + 四重守卫 |
| 文档一致性 | `.ai/` 四文档 + README + docs/ 交叉比对 | `.ai/` 准确；README 有 N-2 漂移 |
| Finding 复判 | 旧基线 18 项逐项源码复核（3 路并行取证） | FIXED 10 / PARTIAL 2 / OPEN 6 / NOT REPRODUCED 1 |

**未能执行项**：代码覆盖率量化 —— venv 无 `coverage` / `pytest-cov`，且 `requirements/dev.txt` 未声明（属既有缺口 T-2，未擅自安装依赖）。

---

End of PROJECT_HEALTH_CHECK_2026-09-10.md
