# DOCUMENTATION_AUDIT.md — 全面工程健康审计 · 文档、需求与代码一致性审计（Stage 5）

- **审计日期**: 2026-09-28 ｜ 对象: HEAD `2823d1c` ｜ 性质: READ-ONLY
- **方法**: `.ai/` 四文档 + rules + docs/ 全树逐文档 vs 代码事实（grep 关键词 + 结构比对 + 数值核对）；仓库外文档资产（`D:\workFile\`）实地核对；SSOT 链（需求→设计→ADR→实现→测试→状态）逐环节追踪

---

## 1. SSOT 链现状 [VERIFIED]

| 环节 | 承载文档 | 状态 |
|---|---|---|
| 需求 | `people-import-face-clustering-development-plan.md`（仓库内）+ `D:\workFile\photo-archiver\01-Product\`（仓库外 PRD 系） | 仓库内计划完好；仓库外 PRD 与仓库现状偏离度未逐页核（UNKNOWN，历史文档集 2026-07-01） |
| 设计/裁决 | 开发计划 + 执行计划 + `.ai/ARCHITECTURE_DECISIONS.md` | 计划完好；**ADR 止于 041（2026-09-13），阶段 C–F 期间裁决（E-SG-6、inclusive>=、D-3 兼容写入、BLK 系）零登记** |
| 实现 | `src/`（HEAD 2823d1c） | 基准 |
| 测试 | `tests/`（1310/6/0） | 基准 |
| 状态 | `.ai/PROJECT_STATUS.md` | **v1.34.1 / 2026-09-23 —— 滞后 HEAD 5 天、6 个开发会话** |
| 业务基线 | `D:\workFile\PhotoArchiver-BusinessReview\` Stage1→Stage4.2 | **已对齐 2823d1c（"全文行号按 HEAD 重核 ✅"），但完全在仓库外**（AUD-003） |

## 2. 逐文档核验表（AUD-001 量化）

| 文档 | 自称版本/日期 | vs HEAD 事实 | 判定 |
|---|---|---|---|
| `.ai/PROJECT_STATUS.md` | v1.34.1 / 09-23 | §1 路线图表止于"阶段 B–F 待立项"；§2 当前步 = 阶段 B 性能 P0；§4 能力表 12 行**止于阶段 B**（无 C/D/E/F 行）；§5 Last Session = 09-23、质量门记 **1104 tests**（实际 1310）；§6 Next Step 仍在问"阶段 C 是否立项"；§7 迁移链"001→002→003"（实际 8 个） | **全面滞后**（7 个章节全部过期） |
| `.ai/KNOWN_ISSUES.md` | v1.16.0 / 09-21 | 无 Open issue；LIMIT 表未随阶段 C–F 复审；LIMIT-006 双表重复承载（AUD-005） | 滞后+重复承载 |
| `.ai/ARCHITECTURE_DECISIONS.md` | v1.2.0 / 止于 ADR-041 | E-SG-6（(person,photo) 归档去重）、D-3 兼容写入、inclusive 合并门限、BLK-1/5 语义变更（migration 008 属 schema 级决策）**均无 ADR** | 关键决策未文档化 |
| `.ai/DOCUMENT_INDEX.md` | v1.3.1 / 07-26 | stage-f-calibration-report、evidence/、acceptance 脚本、本审计产物均未登记 | 导航失效 |
| `docs/user-guide/manual.md` | 覆盖至阶段 A/B（自述"v2.8.0 之后的源码更新"节） | 聚类/配对工作台/重新分析/失败清单 **0 命中**——阶段 C–F 六项用户可见功能（识别运行重试入口、聚类、配对工作台、结果查看、失败清单导出、历史回填 CLI）零手册覆盖 | 用户文档缺口 |
| `docs/user-guide/workflow.md` / `faq.md` | — | 同上关键词 0 命中 | 同上 |
| `docs/development/stage-f-calibration-report.md` | Stage F 交付物 | `match_threshold` **0 命中**（F1-2 证据侧缺口坐实；D-2 边界实测 0.39/0.40/0.41 仅存在于仓库外 Stage4_2 报告） | 证据链断裂 |
| `CHANGELOG.md` | 止于 [2.8.0] 09-13 | 47 个 tag 后提交（含阶段 A–F 用户可见功能）无记录、无 Unreleased 段 | 发布记录缺失（AUD-002） |
| `README.md` | — | 结构/命令与实际一致 ✅；但声明 pre-commit 属开发栈（实际无配置，AUD-007）；"当前进度唯一权威"指向过期 PROJECT_STATUS | 部分失真 |
| `.ai/rules/dependency-rules.md` §4 | 自称权威矩阵 | 与代码/守卫测试三方矛盾（AUD-009，Stage 1 已立案） | 真实矛盾 |
| `docs/roadmap/DEVELOPMENT_ROADMAP.md` | 基线 3a2ef0a（09-02） | "Current State"章节以现在时描述 09-02 状态（570 tests、"3 项功能失效"、无 WAL 等）——**该状态此后全部修复**，无历史标记 | 见 AUD-022 |
| `docs/roadmap/NEXT_PHASE_FEATURE_DEVELOPMENT_PLAN.md` | 基线 4c0cc8c（09-02） | 缺口表"照片删除/库管理 MISSING（照片只进不出）"——**现已被 delete_photos_service + 照片库删除入口实现**，行文仍为待办 | 见 AUD-022 |
| `docs/architecture/overview.md`、`docs/deployment/project-structure.md` | v1.1 / 07-19、07-24 | 分层描述与实际一致（审查过的关键章节）；结构文档声明以 ARC §4 为权威且自认人类入口 | 基本一致 |
| `.ai/rules/` 其余 8 份 | — | coding/worker/ui 等规则与代码抽查一致（WRK-002 由守卫测试强制） | 基本一致 |

## 3. 仓库外文档资产核对 [VERIFIED]（AUD-003 深化）

`D:\workFile\PhotoArchiver-BusinessReview\`（8 份，6 份更新于 2026-09-28）：

- **Stage1_BusinessFacts / Stage2_BusinessRules / Stage3_BusinessDiagrams / Stage4_FinalAudit / Stage4_1_FinalReview / Stage4_2_FinalFreezeReview** 已全部声明基线 `2823d1c` 并"行号按 HEAD 重核"。
- **Stage4_2 冻结判定（§9）**：8 项冻结条件全部 ✅——①基线一致；②Stage4 BLK-1..5 关闭（真库探针：BLK-1 5/5、008 回填 4/4 情形）；③Stage4.1 BLK-3R/D1D/D2D 关闭；④Stage1-3 与 HEAD 一致（引用机械校验 0 越界）；⑤D-1 七层一致 + D-2 边界实测（0.39 不命中/0.40/0.41 命中，文档 12 处全为 `>=`）；⑥无新高严重度错误；⑦剩余均为有界 Known Limitation；⑧13 张 Mermaid 图 [IMPL] 节点可指认。新发现仅 NF-1/NF-2 两项低危引用偏移。
- **风险**：项目业务基线的**唯一**现行版本、冻结判定与 D-2 校准证据均在仓库外且不受 git 管理（丢失/分歧无版本保护）；仓库内 `stage-f-report-verification.md`（untracked）仅为其中一环的核验记录。

## 4. 阶段收尾义务的登记载体缺失

Stage-F 审查引用的"§0.6 阶段收尾义务"（每个阶段收尾须同步 PROJECT_STATUS/KNOWN_ISSUES/manual/ADR/DOCUMENT_INDEX）**在仓库内任何文档中不存在该条款**（执行计划 grep 收尾义务 = 0 命中）——义务本身只存在于会话内的审查报告。这解释了 AUD-001 为何反复发生：**同步义务无权威书面登记**，全靠会话记忆。

## 5. 发现

- **AUD-022（P3）历史规划文档无历史标记**：`DEVELOPMENT_ROADMAP.md`（"Current State" 以现在时描述 09-02 已修复状态）与 `NEXT_PHASE_FEATURE_DEVELOPMENT_PLAN.md`（"照片删除 MISSING" 与现状矛盾）。二者为规划快照，但无"历史快照，现状以 X 为准"声明，AI/新人按图索骥会误判。
- **AUD-001 证据扩充（P1 维持）**：量化后 PROJECT_STATUS 7 个章节全部过期；ADR/DOCUMENT_INDEX/手册/FAQ/工作流五类文档同损；根因链清晰 = §4 的收尾义务无书面登记。
- **AUD-004 状态更新**：F1-2 证据侧缺口**坐实**（仓库内 calibration report 0 处 match_threshold）；但 D-2 边界证据存在于仓库外 Stage4_2（0.39/0.40/0.41 实测）——证据存在但不在证据应在的位置。
- **AUD-002 佐证**：47 提交无 CHANGELOG 记录，与手册缺口叠加 = 阶段 C–F 在"用户可感知文档面"整体缺席。

## 6. 结论

文档体系的**骨架与治理方法论是健全的**（SSOT 指定、阅读顺序、审计方法论、维护规则俱全），但**阶段 C–F 的六个开发会话完全未履行文档同步**：状态文档、ADR、导航索引、用户手册、CHANGELOG 五面同时滞后，且唯一现行业务基线在仓库外。滞后的根源不是"忘了"而是"义务未登记"。修复路径明确且机械：以仓库外 Stage1–4.2 为源回填仓库内五文档 + 补 ADR + 登记 DEP 矩阵（AUD-009 一并），预计一个工作日内可完成；**在此之前，PROJECT_STATUS 不得作为决策依据**。
