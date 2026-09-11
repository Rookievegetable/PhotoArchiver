# Phase F 开发计划 — 正确性收口与发布就绪（Correctness & Release Readiness）

> Version: 1.1 · 2026-09-12 · 状态：**已裁决开工**（owner 2026-09-12 按建议批准 D1–D9；其中 D1/F-4 路径锚定已由 Phase F 前三候选落地，D4–D9 登记 ADR-036）
> 依据：`docs/health-check/PROJECT_HEALTH_CHECK_2026-09-10.md`（本轮体检，HEAD `a03ce25` / v2.4.0）
> 工作量估算：**12 工作日**（含 F-4 路径锚定）/ **9 工作日**（不含 F-4）· 风险：中（触碰配置默认值语义与 Domain 值对象，需 ADR 先行）

---

## 1. 目标

把项目从「**Beta Ready**」推进到「**Release Candidate**」：清掉体检报告中 **6 项 OPEN** 与 **3 项用户可达新发现**，使"换台机器、换个目录、用中文人名、扫描 U 盘"这些真实场景不再出问题。

**本阶段不新增业务能力**（除 CLI 对等补齐），全部为正确性、健壮性与质量可见性收口。

体检判定对照：Release Candidate 当前差 4 项——库路径绝对锚定（F-7）、Windows 文件名净化（F-10）、插件动作可见性（N-1）、README 修订（N-2）。本计划覆盖其中 3 项（F-7 / F-10 / N-2）；**N-1 插件可见性是产品定位问题而非缺陷，不在本阶段，建议 owner 单独裁决**（见 §8 Out-of-Scope）。

---

## 2. 实证基础（每项缺陷的复现路径与代码位置）

> 全部结论基于 HEAD `a03ce25` 源码实测，不采信 2026-09-02 旧基线结论。

| 编号 | 缺陷 | 复现条件 | 代码位置 | 用户后果 |
|---|---|---|---|---|
| **F-10** | Windows 保留名 / 非法字符未净化 | 人员名为 `con`/`nul`/`com1`，或源文件名为 `nul.jpg`；任何 Windows 归档 | `domain/value_objects/archive_path.py:39-74`（仅 strip + 拒分隔符 + 拒 `.`/`..`） | 归档项**系统性 FAILED**（被逐项 OSError 隔离兜底，但持续失败，用户只见"部分失败"） |
| **F-11** | junction / symlink 环路递归 | 扫描含 junction 的目录（Windows 常见：用户目录、U 盘） | `infrastructure/filesystem/local_photo_file_scanner.py:27-32`（`folder.glob("**/*")`，Python 3.11 的 `**` 会跟随目录链接） | 递归失控 / 重复扫描；无防护 |
| **F-13** | `search()` JOIN 无 DISTINCT | 同一照片有多条 recognition_results（多张人脸） | `infrastructure/database/sqlite_photo_repository.py:195-198` | 照片列表/筛选结果**同一照片重复出现** |
| **F-13b** | "未匹配"哨兵未实现 | 试图筛选"没有识别结果的照片" | docstring 承诺见 `domain/value_objects/photo_search_criteria.py:38-39`，实现缺失 | 文档承诺 ≠ 行为 |
| **N-3** | 导入任务无 cancelled 接线 | 执行人员导入 → 点取消 | `import_people_controller.py:51`（`connect_signals` 不接受 cancelled 参数）；scan 已修（`main_window.py:501,515-520`） | UI 停在 "Cancelling..." 不复位，按钮不可用 |
| **N-3b** | 导出无取消通道 | 导出大库 → 点取消 | `main_window.py:784-786` | Cancel 无效，只能等完成 |
| **F-7** | 路径 CWD 相对 | 从不同目录启动；macOS Finder 启动（CWD=`/`） | `settings.py:19`（`sqlite:///data/photo_archiver.db`）、`:20`（`resources/models`）、`:47`（`env_file=".env"`）；日志目录 `logging/configuration.py:10`（`Path("logs")`） | **静默换库**——用户认为"数据丢了"。当前仅 `bootstrap.py:42` 启动警告兜底 |
| **N-2** | README 自相矛盾 | 阅读 README | `README.md:270-285`（"待实现"列出已完成的 Step 14/15 与 Alembic）、`:267`（"226 passed / 8 skipped"，实为 713 collected）、`:264-265`（重复行） | 人类第一入口可信度受损 |
| **T-2** | 无覆盖率度量 | — | `requirements/dev.txt` 无 pytest-cov；venv 无 coverage 模块 | 盲区不可量化（本轮体检因此无法给出覆盖率数字） |
| **T-1/T-5** | 无共享 conftest；CI no-skip 守卫用收集期统计 | — | 全仓无 `tests/conftest.py`（约 12 处重复装配）；`ci.yml:86-107` 用 `pytest --co -q`（不含运行时 importorskip） | 装配重复；守卫效力存疑 |

### 2.1 对上一轮 N-4 的更正（重要）

体检报告 N-4 记"CLI 启动无备份快照"。复核 `docs/development/configuration.md:98` 后确认：**"CLI 子命令不生成启动备份"是已文档化的既定行为**（Phase B D-B3 语义），并非遗漏。

→ N-4 从"缺陷"降级为"**待裁决的行为选择**"，本计划纳入裁决点 **D8**，不再作为默认修复项。

### 2.2 既有裁决约束

`bootstrap.py:93` 记录 **D-B5（Phase B）：完整路径锚定已从 P0 降级为 P1**，本轮仅做启动警告。本阶段若要实施 F-4 路径锚定，**属于重开 D-B5，须 owner 明确授权**（裁决点 D1）。

---

## 3. ADR-035 裁决点（D1–D9，每点附建议，**待 owner 拍板**）

### D1 是否本阶段实施路径锚定（重开 D-B5） —— 建议：**是，实施**
理由：启动警告只是"事后告知"，不能阻止"换目录=换库"这个最伤用户的结果；体检把 F-7 列为 macOS 发布阻塞项。若 owner 仍维持 P1，则 F-4 整体移出本阶段（工期 -3 天）。

### D2 锚定目标 —— 建议：**用户数据目录（跨平台标准位），零新依赖**
用标准库实现，不引入 `platformdirs`（roadmap §13.5 禁止新依赖）：
- Windows：`%LOCALAPPDATA%/PhotoArchiver`（回退 `~/AppData/Local`）
- macOS：`~/Library/Application Support/PhotoArchiver`
- Linux：`$XDG_DATA_HOME/PhotoArchiver`（回退 `~/.local/share/PhotoArchiver`）

备选（否决）：锚定到应用安装目录（`main.py` 所在目录）——会让"clone 一份代码就共享一个库"，且多处 clone 互相污染。

### D3 旧 CWD 库的迁移策略 —— 建议：**启动探测 + 一次性迁移提示，不自动搬移**
在新位置上电时，若 CWD 下存在 `data/photo_archiver.db` 而新位置无库，弹一次对话框说明"发现旧位置数据库，是否迁移"，用户确认后复制过去（复用既有 `backup.py` 的 `VACUUM INTO` 能力）；绝不自动移动用户数据。若用户拒绝，保持新库并在日志与 UI 说明。

### D4 Windows 保留名 / 非法字符净化策略 —— 建议：**静默替换为安全名 + 审计日志，不拒绝**
- 非法字符 `: * ? " < > |` 与控制字符 → `_`
- 尾点 / 尾空格 → 去除
- 保留设备名（去掉扩展名后匹配 `CON PRN AUX NUL COM1-9 LPT1-9`，大小写不敏感）→ 前缀 `_`（`con.jpg` → `_con.jpg`）
- 净化发生在 **Domain `ArchivePath`**（纯字符串逻辑，零文件系统/零框架，符合 Domain 零依赖约束）；`event_or_date` 由 builder 生成为 `%Y-%m-%d`，天然安全，无需处理
- 净化结果写入归档记录并在 loguru 记一行，便于追溯

否决备选：抛 `ValidationError` 让该项 FAILED —— 会让"人名叫 con"这类合法输入持续失败，是把内部平台限制转嫁给用户。

### D5 junction / symlink 环路防护 —— 建议：**环检测（visited realpath 集合）+ 深度上限，不跟随链接目录**
用迭代式 `os.scandir` 遍历替代 `glob("**/*")`；进入目录前用 `os.path.realpath` 查 visited 集合，命中即跳过；另设可配深度上限（建议默认 32）。
理由：环检测**同时覆盖 symlink 与 junction**，无需解析 Windows reparse tag 这类平台特判（跨平台可维护）。
否决备选：仅 `is_symlink()` 跳过 —— **Windows junction 的 `is_symlink()` 返回 False**，防不住。

### D6 "未匹配"哨兵 —— 建议：**实现（LEFT JOIN ... IS NULL），而非删除 docstring 承诺**
该能力对长期运营有实际价值（找"还没识别过的照片"），实现成本低于改写文档承诺的沟通成本。

### D7 导出取消通道 —— 建议：**本阶段实现**
导出是全内存 + openpyxl 整簿，大库耗时可达分钟级；无取消通道是真实的可用性断点。实现沿用既有 `raise_if_cancelled` 任务边界粒度（LIMIT-002 同型，不追求逐行取消）。

### D8 CLI 是否生成启动备份 —— 建议：**是，与 GUI 对齐**
`configuration.md:98` 现记为"CLI 不生成"。CLI 同样会写库（`scan` / `prune-missing --execute` / `backfill-content-hash`），风险面与 GUI 同量级，建议对齐；若 owner 维持现状，则只补文档说明不动代码。

### D9 版本号 —— 建议：**v2.5.0（minor）**
本阶段含新增能力（CLI `import-people` / `export` 子命令、"未匹配"筛选）；若 owner 裁掉 CLI 与哨兵仅留修复，则应为 **v2.4.1（patch）**。

---

## 4. 实施分期与工作量

| 期 | 内容 | 交付 | 估时 |
|---|---|---|---|
| **F-0** | **ADR-035 定稿**：D1–D9 经 owner 拍板后落 `docs/development/phase9-adr-draft.md` → 登记 `ARCHITECTURE_DECISIONS.md` | ADR-035 Accepted | 0.5 天 |
| **F-1** | **Windows 文件系统语义收口**：`ArchivePath` 段净化（D4：非法字符 / 尾点空格 / 保留设备名）+ 审计日志；扫描器改为迭代遍历 + visited realpath 环检测 + 深度上限（D5） | 归档不再因人名/文件名系统性失败；junction 不再递归失控 | 2 天 |
| **F-2** | **查询正确性**：`search()` 去重（DISTINCT / GROUP BY photos.id）；"未匹配"哨兵实现（D6）；补齐对应集成测试 | 筛选结果无重复行；哨兵可用 | 1 天 |
| **F-3** | **取消与 UX 收尾**：导入 cancelled 信号接线 + 终态复位；导出取消通道（D7）；照片列表空态占位；审核行显示姓名/文件名替代裸 UUID；语言占位控件按 D8' 处置（见 §8） | 取消可用；空态与可读性改善 | 2.5 天 |
| **F-4** | **路径锚定（条件期，D1 授权才做）**：用户数据目录解析（D2）+ 三处相对默认值（DB / 模型 / 日志）锚定 + `.env` 按用户目录加载 + 旧库探测与迁移提示（D3）；**全部走 ADR-010/022/031 语境复核** | 换目录/从 Finder 启动不再换库 | 3 天 |
| **F-5** | **质量基建**：`requirements/dev.txt` 加 pytest-cov（唯一新增开发依赖）+ 记录覆盖率基线（**不设门槛，先可见**）；`tests/conftest.py` 共享真实 SQLite fixture（T-1）；CI no-skip 守卫改为运行期统计（T-5） | 盲区可见；装配收敛；守卫有效 | 1.5 天 |
| **F-6** | **CLI 对等**：`import-people` / `export` 子命令（复用既有 Application 服务，零新边界）；CLI 启动备份（D8） | CLI 覆盖主工作流 | 2 天 |
| **F-7** | **文档收口 + 回归 + 发版**：README 修订（删除矛盾"待实现"段、计数指针化、补 `.csv`/`.xlsm` 说明）；user-guide / FAQ 同步；全量回归 + 发版 **v2.5.0**（或 v2.4.1，按 D9） | 发版 | 1.5 天 |

**合计 ≈ 12 工作日**（含 F-4）；不含 F-4 ≈ **9 工作日**。

> F-1 / F-2 / F-5 / F-6 相互独立，可并行或调换顺序；F-4 与 F-7 的文档部分依赖 D3 结论。

---

## 5. 架构影响

| 期 | Domain | Application | Infrastructure | Presentation | 新依赖 | Schema | 配置格式 | ADR |
|---|---|---|---|---|---|---|---|---|
| F-1 | **是**（ArchivePath 段净化，纯字符串） | 否 | **是**（扫描器遍历） | 否 | 否 | 否 | 否 | **需要**（D4/D5） |
| F-2 | 否 | 否 | **是**（SQL 去重 + 哨兵） | 否 | 否 | 否 | 否 | 不需要 |
| F-3 | 否 | 否 | 否 | **是** | 否 | 否 | 否 | 不需要 |
| F-4 | 否 | 否 | **是**（settings + 日志目录） | 可能（迁移提示） | 否 | 否 | **是**（默认值语义） | **需要**（D1-D3，ADR-010/022 语境） |
| F-5 | 否 | 否 | 否 | 否 | **是**（pytest-cov，dev-only） | 否 | 否 | 不需要（需 owner 批准 dev 依赖） |
| F-6 | 否 | 否 | 否 | 否（`main.py`） | 否 | 否 | 否 | 不需要 |

**红线**：零 schema migration、零运行时新依赖、零公开 API 破坏性变更、零架构边界变更。F-1 的净化函数必须是纯字符串逻辑（Domain 侧不得引入 `os`/`pathlib` 文件系统调用）。

---

## 6. 测试矩阵（全量不减红线）

| 期 | 必须新增的测试 |
|---|---|
| F-1 | 保留设备名矩阵（CON/PRN/AUX/NUL/COM1-9/LPT1-9 × 大小写 × 带扩展名）；非法字符与尾点尾空格；净化后路径仍唯一（不引入碰撞）；`event_or_date` 不受影响；junction 环检测（构造自引用目录 → 不死循环）；深目录深度上限；既有归档路径测试不回归 |
| F-2 | 一照片多识别行 → 列表只出现一次；"未匹配"哨兵筛选正确；与人员/日期轴组合（三轴 AND）不破坏既有矩阵 |
| F-3 | 导入取消 → 终态信号发射 + UI 复位；导出取消 → 任务边界终止 + 无半文件（原子写已保障）；空态渲染；审核行显示姓名/文件名 |
| F-4 | 三平台路径解析（Windows/macOS/Linux 用 monkeypatch 环境变量）；换目录启动指向同一库；旧库探测与迁移提示（确认/拒绝两路径）；`.env` 从用户目录加载 |
| F-5 | 覆盖率基线图（仅记录）；conftest fixture 被 ≥3 个模块复用；CI 守卫能捕获人为制造的运行期 skip |
| F-6 | CLI import-people（txt + xlsx）；CLI export（ALL + FILTERED）；CLI 启动备份生成 |

**既有 713 用例全量不减**（当前基线 710 passed / 3 skipped / 0 failed）。

---

## 7. 验收标准

1. Windows 上人员名 `con`、`nul`，或源文件 `nul.jpg`，归档**成功且文件名安全**，无系统性 FAILED；
2. 扫描含 junction 的目录不死循环、不重复注册；
3. 照片列表/筛选结果中同一照片不重复出现；"未匹配"筛选可用；
4. 导入与导出可取消，取消后 UI 状态正确复位；
5. （若 D1 通过）从不同目录启动、macOS Finder 启动，均指向同一数据库；旧库可被发现并按用户选择迁移；
6. 覆盖率基线已记录；CI 守卫对运行期 skip 生效；
7. CLI 覆盖 import-people 与 export；
8. README 无与现状矛盾的表述，测试计数指针化；
9. 既有 713 用例全量不减，ruff / mypy / pip check 三门全绿；
10. `git diff` 复核：零 schema、零运行时新依赖、零公开 API 破坏性变更。

---

## 8. Out-of-Scope（本阶段明确不做）

- **N-1 插件动作可见性**：产品定位问题（对外承诺 vs 开发者扩展点），非缺陷。建议 owner 单独裁决后另起一轮——要么接入可配置插件目录并调用 `_add_plugin_actions()`，要么收回 README/FAQ 宣传。
- **CURRENT_BATCH 导出 / 批次持久化**：roadmap §13.12 owner 门控，AI 不得自行实施。
- **安装态分发（ADR-031 方案 B）**：需求信号未触发。
- **i18n 实装**：roadmap §13.7 明示不做。语言占位控件本阶段仅做 D8' 二选一——**移除控件**或**标注 Out-of-Scope 提示**，不做实装。
- **大库导出流式化（P2-9）**：YAGNI 门，仅当真实用户报内存问题。
- **并行匹配分片 flush（P1-1 / F-8）**：默认 `max_workers=1` 已规避；本阶段不触碰识别管线（避免与 ADR-032/033 既有调优叠加风险）。**建议下一轮处理**。
- **缩略图孤儿缓存清理（N-8）**：低优先级技术债，可与 F-5 conftest 轮合并或延后。
- **导入去重键修正（N-5）**：影响面需单独评估，本阶段不动。
- **LIMIT-001 / 002 / 004 / 006**：登记在案的设计与测试覆盖限制，维持不修。

---

## 9. 风险与缓解

| 风险 | 级别 | 缓解 |
|---|---|---|
| F-4 改变默认库位置 → 用户"找不到旧数据" | **高** | D3 旧库探测 + 迁移提示（绝不自动搬移）；ADR 明确记录；`.env` 显式配置始终优先于默认值 |
| F-1 净化规则改变既有归档路径 → 已归档文件与库内记录分歧 | 中 | 净化仅影响**新归档**；存量 `archive_records` 不动；补齐"净化前后"对照测试防碰撞 |
| F-1 扫描器改遍历 → 性能回退（glob 为 C 层实现） | 中 | 保留 `os.scandir`（同为 C 层）；用 2000 文件目录做前后对比基准（`tools/` 已有 bench 惯例） |
| F-5 引入 pytest-cov → CI 时间增加 | 低 | 仅 dev 依赖；CI 可先只在 Linux job 采集 |
| F-4 触碰 ADR-010/022 语境 | 中 | ADR-035 显式记录与既有 ADR 的关系，不推翻只细化 |
| macOS CI 段错误复发（LIMIT-006） | 低 | 新增测试避免"背靠背大目录压力扫描 + teardown 并发"形态；复发则按既定 darwin skip 模式处置 |

---

## 10. 执行顺序与提交策略

```text
F-0 ADR 定稿（owner 裁决）
   ↓
F-1 Windows 语义 ──┐
F-2 查询正确性   ──┼─→ 各自 targeted 测试 → 全量回归 → 独立提交
F-5 质量基建     ──┘
   ↓
F-3 取消与 UX（依赖 F-1/F-2 稳定）
   ↓
F-4 路径锚定（D1 授权；独立提交，不与修复混提）
   ↓
F-6 CLI 对等
   ↓
F-7 文档收口 + 全量回归 + 发版
```

提交约定：每期一个 Conventional Commits 提交（如 `fix(domain): sanitize Windows reserved names in archive path segments`），**F-4 单独提交**便于回滚；每期结束时刷新 `.ai/PROJECT_STATUS.md`。

---

## 11. Owner 裁决清单（开工前置）

- [ ] **D1** 是否本阶段实施路径锚定（重开 D-B5 降级裁决）——建议：是
- [ ] **D2** 锚定目标：用户数据目录（零新依赖标准库实现）——建议：用户数据目录
- [ ] **D3** 旧 CWD 库迁移策略：启动探测 + 用户确认后迁移，不自动搬移——建议：同意
- [ ] **D4** Windows 净化策略：静默替换为安全名 + 审计日志（不拒绝）——建议：同意
- [ ] **D5** junction 防护：环检测（visited realpath）+ 深度上限，不跟随链接目录——建议：同意
- [ ] **D6** "未匹配"哨兵：实现（LEFT JOIN IS NULL）而非删除文档承诺——建议：实现
- [ ] **D7** 导出取消通道：本阶段实现——建议：实现
- [ ] **D8** CLI 启动备份：与 GUI 对齐（修改 `configuration.md:98` 既定行为）——建议：对齐
- [ ] **D8'** 语言占位控件：移除 / 标注 Out-of-Scope（二选一）——建议：标注 Out-of-Scope
- [ ] **D9** 版本号：**v2.5.0**（含新能力）或 **v2.4.1**（仅修复）——建议：v2.5.0
- [ ] **F-5 新增 dev 依赖 pytest-cov**（唯一新增依赖，dev-only）——建议：批准

> **N-1 插件可见性不在本清单**：属独立产品定位决策，建议 owner 另行裁决后单独立项。

---

End of phase-f-correctness-plan.md
