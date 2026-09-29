# Stage F 冻结审查报告（§1–§18）真实性核验记录

- **核验对象**：《Stage F 最终独立验收与冻结审查报告（§1–§18）》（2026-09-26，判 **FAIL / 0×P0 + 4×P1**，下称「被核验报告」；该文本目前仅存在于会话中，未落盘——盘上 untracked 的 `stage-f-acceptance-review.md` 是其**上一版**「CONDITIONAL PASS」报告，非同一文本）
- **核验方式**：只读——独立复跑全部质量门禁 + 逐锚点读码/读文档/读证据 JSON + git 取证；未修改任何 tracked 文件
- **核验日期**：2026-09-28（取证跨 2026-09-27/28）
- **核验结论**：**被核验报告真实可信。** 四项 P1（F1-1…F1-4）、全部证据数字、代码与文档锚点经独立复核成立；FAIL 判定维持。发现 **4 处外围瑕疵**（1 哈希笔误 / 1 skip 归因错误 / 1 不可复现命令 / 1 不存在的文件引用），均不改变判据、判级与 §17 修复边界。

## 1. 独立复跑（本核验亲自执行）

| 项 | 命令 | 本轮结果 | 报告声称 | 判定 |
|---|---|---|---|---|
| 全量测试 | `python -m pytest -q` | **1292 passed / 6 skipped / 228.80s**（二跑 `-rs` 234.64s，均 exit 0） | 1292 / 6 / 227.39s | ✅（时长为运行噪声） |
| Lint | `ruff check src tools tests` | All checks passed | 同 | ✅ |
| 类型 | `mypy src` | Success, 258 source files | 同 | ✅ |
| 行尾/空白 | `git diff --check` | exit 0 | 同 | ✅ |
| 工作区 | `git status --porcelain` | 仅 1 个 untracked（= 上一版评审报告） | 同 | ✅ |
| 基线 | `git log` | HEAD=`b3b8685`；Wave 1/2/3 与基线提交顺序、提交信息均吻合 | 同（哈希笔误除外，见 §3-1） | ✅ |

## 2. P1 判据逐项复核（全部成立）

### F1-1 端到端回归未贯通 — ✅ 成立
- `tools/validate_stage_f.py`（共 390 行）：:272-276 确实用 `repositories.people.add(Person(...))` 直造名单，**绕开 Stage A 导入与确认**；:334-348 止于 `ArchivePlanner.plan()`，:355 即 `return`，**全文无 ArchiveExecutor**。
- 全仓 `ArchiveExecutor` 实例化仅三类：`app/services.py:172`（UI 组合根）、`tests/integration/test_step11_archive_e2e.py:138/185/217/250`、假仓储单测。step11 在 **:109** 恰为 `recognition.approve()` 旧审核路径，非 Stage E 确认。
- **同时含 `PairingWorkbenchService` 与 `ArchiveExecutor` 的测试文件交集 = 空**（grep 交叉验证）→ 无任何测试走 confirm()→execute()。
- 真实生产库副本 `archive_records` before=0 / after=0 → 归档链历史上从未真实落盘。

### F1-2 match_threshold 校准交付缺失 — ✅ 成立
- `application/dtos/settings.py:12` `DEFAULT_MATCH_THRESHOLD = 0.40`；`app/services.py:375` 注入 `CosinePersonMatcher(threshold=settings.match_threshold)`。
- `match_threshold` 在校准报告、`docs/development/evidence/`、`.ai/` 全部 **0 命中**（grep）。

### F1-3 §0.6 阶段收尾义务违约 — ✅ 成立
- `PROJECT_STATUS.md` v1.34.1/2026-09-23：正文「阶段 A…已实施完成，**阶段 B–F 待逐阶段立项**」；Next Step 原文仍在问「**阶段 C（多脸检测与可重跑）是否立项**」→ 与 HEAD 相反。
- `docs/user-guide/manual.md`：:59-60 导航六项；:119 自陈覆盖至 Stage A/B；关键词 聚类 / 配对工作台 / 重新分析 / 失败清单 / 重新聚类 **全部 0 命中**。
- `KNOWN_ISSUES.md` v1.16.0/2026-09-21；`.ai/` 全目录 `E-SG` **0 命中**。
- `ARCHITECTURE_DECISIONS.md` v1.2.0/2026-09-06，止于 ADR-040/041（2026-09-13 追记）；无 D3 兼容写入 / E-SG-6 / inclusive>= 任何条目。
- `DOCUMENT_INDEX.md` v1.3.1/2026-07-26；`stage-f` / `calibration` / `evidence` / `acceptance` **0 命中**。

### F1-4 废弃 Top-1 归档规则残留 3 载体 — ✅ 成立
- `archive_planner.py:96-98` docstring「planned **at most once** … first APPROVED match … 1:N Top-1」与同文件 :106-108「**(person, photo)** 归档去重作用域」自相矛盾（逐字核实）。
- `face-recognition-pipeline-and-archive.md:249-250`、`plugin-context-design.md:211` 原文残留（后者把废弃规则列为插件不可篡改的业务不变量）。

## 3. 差异清单（4 项——采纳报告时需更正；均不改变判定）

1. **哈希笔误**：报告 3 处写 `f6d70b0`；实际提交为 **`f6e70b0`**（`f6e70b08a414…`）。提交信息与报告所引逐字吻合（E-P1-1/E-P1-2/E-P2-1 兼容层修复），属一位字符笔误，非虚构。
2. **§12 skip 归因与事实不符**：本机 `pytest -rs` 实测 6 skip = **4×「symlink creation not permitted on this platform/account」**（test_archive_executor_symlink ×3 + test_local_photo_file_scanner ×1）+ **2×「PA_STRESS 专用 job 门控」**（test_scan_stress_no_qtbot）。报告所写「onnxruntime 缺失」「PHOTOARCHIVER_WITH_PYTEST 未设」两类**不存在**：后者全仓 0 命中；insightface 真模型用例在本机实际执行（测试日志含其运行期告警）。其定性结论「6 项全部环境性/平台性、无该跑未跑」**仍然成立**。
3. **§12 定向子集命令按字面不可执行**：裸名传参 → `ERROR: file or directory not found: test_upgrade_integrity`；「49 passed in 1.52s」无法按原命令复现。按显式路径复跑同域子集 = **70 passed / 3 skipped / 3.28s**（「test_archive」片段的文件选集差异所致）。定性结论（定向子集全过、秒级完成）不受影响，但该数字不可核。
4. **§11.3 引用不存在的文件**：`PROJECT_STATE.json`（schema v1.3、无 stage 字段）在仓库内**不存在**（全树 find 0 命中）。其推论「仓库内不存在可解析的最新冻结规则节点」反而更强。
- 附注 a：个别行号 ±1–3 行漂移（如 people.add 循环实际 :273-276 vs 所引 :272-277；失败分类常量使用行 :89 vs 所引 :92），不影响实质。
- 附注 b：§2.1「冻结面 diff（6 files +111/−12）」经 `git diff --numstat` **精确复算成立**：pairing_workbench(+57/−3) + archive_planner(+15/−9) + recognition_repository(+14) + archive_record_repository(+8) + cluster_assignment_repository(+8) + person_repository(+9，Wave 2) = **+111/−12**；前 5 文件全部来自 `f6e70b0`，三 Wave 对其零触碰。

## 4. 其余抽样复核（全部吻合）

- **证据 JSON 三份逐项吻合**：real-run（473 张/1441 脸/44 簇/4 单例/36 簇∈21-50/最大簇<51；扫描 0.96s；识别 83.05s≈5.7 p/s；聚类 8.29s/70.21MB；rerun 44/44；det p10 0.837/p50 0.872/p90 0.908、<0.30 为 0；10 建议/6 确认/199 兼容/199 样本/199 计划/0 跳过）；upgrade-real（546/473/472/**0**/3/544/0 前后不变；8 回填/538 跳过/failures[]/second_noop；003→007）；lifecycle-stress（1000 张；取消延迟 60.0s/elapsed 90.0s/保留 337；663 重试 63.33s；覆盖 1000/1000、跨 run 重叠 0、重复对 0、峰值 79.16MB）。`faces_per_photo{"36":17}` → 17×36=612=**42.5%** 量化成立。
- **阈值锚点**：`face_clustering.py:125/:147/:183` 门语义与 `:169-171` inclusive>= owner 裁决注、`cosine_kernel.py:23/_SIMILARITY_DECIMALS=6、:46 np.round、:67 簇心量化`、`run_recognition_service.py:122 quality_score=det_score`、low-quality 默认 0.0（face_clustering.py:35）——逐行吻合。
- **P2-1 取消排空**：`run_recognition_service.py:68-70` 一次性 submit 全部 → `:72-73` 只 cancel 当前一个 → `:74-79` break → with 退出即 `shutdown(wait=True)` 排空；服务无「检测批」概念（`_OBSERVATION_FLUSH_SIZE` 是 DB 写批量）→ 报告对 §3.4 归因的批评**属实**。
- **P2-5 孤岛**：仓储协议仅 save/find_by_person/list_all；`list_all()` 调用点恰 3 处（match_persons:159、run_recognition:66、delete_person:65——属性名为 `_embeddings`）；`save()` 0 调用点；INSERT 在 sqlite 实现内（:38-46）；真实库 person_embeddings 0 行。
- **P2-3 归档身份**：archive_records DDL 无 person_id、无 UNIQUE(photo_id,target_person_name)，仅 photo_id/status 两索引；upsert 冲突键仅 id（:49-50）；`has_successful_for_person(photo_id, target_person_name)` 字符串等值（:105-118）。
- **P2-4 复核 UI**：整照片缩略图（:203-207 `Path(member.photo_path)`）；presentation 层 crop/bbox 0 命中；成员行仅 photo/index/det/conf（:191-198）；无分页/limit（:143-176）。
- **SG-1/SG-2/SG-3**：「合格成员/合格样本」仅在 exec-plan:205、dev-plan:155 被使用、全规格无定义；004 run_photos 列=(run_id, photo_id, raw_path_snapshot, captured_at_snapshot)+PK(run_id,photo_id)、无 outcome/classification 列；005_recognition_run_error_count.py 存在；`recognition_failure_service` 各锚点（:8-11/:12-15/:16-18/:31/:64-72/:80-94/:103-106）逐行吻合，CSV 4 列固定，retryable=run_photos−observed 纯派生。
- **N-1/N-2**：ADR 寄存器与 KNOWN_ISSUES 无 D3/E-SG-6 条目（grep 证实，寄存器内出现的「D3」均为 Phase 8 删除级联的另一裁决）；test_upgrade_integrity 对 archive_records 做快照但种子 0 行、无「先归档再升级」用例。
- **Wave 清单**：三 Wave 的文件清单与 `git show --stat` 逐项吻合（5/17/7 files；+759/−0、+850/−8、+1068/−0；各文件行数全对）；不含任何冻结服务文件 → 「Stage F 对冻结服务改动 = 0」成立。
- **执行计划锚点**：§F 五条必需项原文核对（确无「人工视觉复核」验收项→§4.4 不阻塞推理成立）；:205「合格成员」、:207-209 E-3、`development-plan.md:193` 逐字吻合。
- **§11.3 三根据**：① PROJECT_STATUS 停在 Stage B；② ADR 寄存器 2026-09-06 + E-SG 0 命中；③ manual 零覆盖——除 PROJECT_STATE.json 引用瑕疵（§3-4）外全部成立。
- **§18 交接事实**：untracked 文件头部确为「**有条件通过（CONDITIONAL PASS）**」的上一版报告（:11），与被核验报告（FAIL）为两份文本。

## 5. 核验判定

> **被核验报告的 FAIL 结论、0×P0 + 4×P1、6×P2、7×SG、§16 冻结契约清单与 §17 修复边界（B-1…B-4）全部维持。**
> 采纳时更正 §3 所列 4 处表述即可；无需对任何判据重新取证。
> Owner 侧未决事项不变：B-1（端到端测试，零 `src/`）、B-2 口径、SG-6 取消排空定性（唯一可能触碰冻结代码的项）、SG-5 人工复核豁免留痕、SG-1/SG-4 语义裁决。
