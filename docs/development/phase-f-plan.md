# Phase F 开发计划 — 数据正确性与长期运营收尾（captured_at 回填 + 路径锚定 + LIMIT-006 诊断）

> Version: 1.0 · 2026-09-08 · 状态：**已拍板动工**（owner 2026-09-08「按建议方案执行」——R1-R4 / A1-A4 / D-1 全部按建议项）
> 依据：v2.4.0 发布后 PROJECT_STATUS §6 立项候选 · 实证基础见各候选节

---

## 0. 裁决记录（owner 2026-09-08，全部按建议执行）

| 候选 | 裁决 |
|---|---|
| **F-1 captured_at 回填** | R1=a 全量重读（EXIF 是事实源，重读幂等）；R2=a 扩 `PhotoRepository.update_capture_time`（与 E-5 `update_metadata` 对称，只动一列）；R3=a dry-run 默认、`--execute` 才写；R4=无 EXIF 者如实计 unchanged（mtime 兜底对齐，不算失败） |
| **F-2 路径锚定 P1** | A1=a `platformdirs.user_data_dir/user_log_dir("PhotoArchiver")`；A2=a 仅改**默认值**锚定 + 旧 CWD 库首启提示（**不自动搬库**——数据安全原则，迁移留给用户手动或后续 `migrate` 子命令）；A3=a 显式 `.env` 配置完全优先（零破坏）；A4=platformdirs 走依赖批准门（ADR-035） |
| **F-3 LIMIT-006** | 本轮仅落 **D-1 诊断收集**（CI macOS 崩溃报告 `.ips` always() 上传）——下次（若有）崩溃即得原生栈；D-2 复现与 D-3 修复（候选：`os.scandir` 重写 scanner）待有 macOS 调试手段时另行推进 |

## 1. F-1：历史照片 captured_at 回填 CLI（≈2 天）

背景：ISSUE-019 修复后新扫描读取正确 EXIF；修复前入库的历史照片 captured_at 可能是 mtime 冒名，而 E-5 `update_metadata` 有意保留快照列——历史错误值无人纠正（归档分桶/时间筛选失真）。

| 分期 | 内容 | 估时 |
|---|---|---|
| C-1 | `PhotoRepository.update_capture_time(photo_id, captured_at) -> int`（Protocol + SQLite/InMemory：只 UPDATE captured_at 列，其余不动） | 0.5d |
| C-2 | `BackfillCaptureTimeService`（先例 BackfillContentHashService：list_all → reader.read → 差异 → 更新；Result：scanned/updated/would_update/unchanged/failed/skipped_missing）+ 测试 | 1d |
| C-3 | CLI `backfill-capture-time`（dry-run 默认）+ CLI 测试 + 指南 | 0.5d |

## 2. F-2：完整路径锚定 P1（≈3 天）

背景：`DEFAULT_DATABASE_URL = "sqlite:///data/photo_archiver.db"` CWD 相对，N4 实证陌生 CWD 启动在彼处另建库/日志（仅警告）→ 真实用户库分裂风险；为 Phase D 形态二（P2-11 用户目录默认值）铺路。

| 分期 | 内容 | 估时 |
|---|---|---|
| P-1 | platformdirs 依赖批准（ADR-035 + §13 + base.txt） | 0.25d |
| P-2 | settings 默认值锚定：`database_url` / `log_directory` 默认改 default_factory（platformdirs 锚定目录），显式 `.env` 完全优先（`model_fields_set` 判定）；显式相对值保留既有警告 | 1d |
| P-3 | 首启引导：旧 CWD 库检测提示（CWD `data/photo_archiver.db` 存在且锚定位置无库 → 打印迁移引导，不自动搬）+ N4 反向集成实证（陌生 CWD + 无显式配置 → 库落锚定目录）| 1d |
| P-4 | 用户指南/FAQ 补章 + 三平台全量回归 | 0.5d |

## 3. F-3：LIMIT-006 诊断收集（D-1，≈0.5 天）

CI macOS job 加 `always()` 崩溃报告上传步骤（`.ips` 诊断文件 → artifact）。后续 D-2/D-3 待 macOS 调试手段立项。

## 4. 验收标准

1. 回填 CLI 幂等且 dry-run 不写；历史照片 captured_at 对齐当前 reader 输出；
2. 默认库路径锚定用户数据目录，陌生 CWD 启动不再分裂库；显式配置零影响；
3. CI 具备 macOS 崩溃报告收集能力；
4. 全量测试不减。

## 5. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 历史值被手工改过被覆盖 | 当前无 captured_at 编辑 UI（值全部来自扫描写入），风险极低；重读幂等 |
| 默认路径变化导致旧用户数据"看不见" | 首启检测旧 CWD 库并打印迁移引导；指南写明手动迁移方法 |
| platformdirs 引入门 | ADR-035 登记 + §13 层归属注（仅 infrastructure/config） |
