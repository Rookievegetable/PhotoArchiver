# Phase E 开发计划 — 库管理与长期运营（P2-1/P2-2/P2-3）

> Version: 1.0 · 2026-09-06 · 状态：**草案待 owner 裁决**（裁决点 D1–D6 拍板后动工）
> 依据：`docs/roadmap/DEVELOPMENT_ROADMAP.md` Phase E（owner 立项门）· 工作量估算 7–12 天 · 风险：高（数据破坏面）——**删除语义 ADR 先行**

---

## 1. 目标

让照片库从"只进不出"变为可运营：**照片/人员可安全删除**（P2-1）、**重扫对账**（P2-2）、**重复照片处置**（P2-3）。底线：删除操作可审计、可从启动备份恢复、绝不误删用户磁盘文件。

## 2. 实证基础：schema 级联矩阵（开发期发现）

读取 `alembic/versions/002_split_create_ddl.py` 确认——**删除语义在 DB 层已由 FK 定义**，且应用连接已开启 `PRAGMA foreign_keys=ON`（有专项测试），级联真实生效：

| 关系 | ON DELETE | 语义 |
|---|---|---|
| photos.folder_id → folders | **SET NULL** | 删文件夹：照片保留、脱离该文件夹 |
| recognition_results.photo_id → photos | **CASCADE** | 删照片：识别结果自动级联删除 |
| recognition_results.person_id → people | **SET NULL** | 删人员：识别结果保留、归属置空（变"未知人员"） |
| person_embeddings.person_id → people | **CASCADE** | 删人员：人脸嵌入自动删除 |
| archive_records.photo_id → photos | **CASCADE** | 删照片：归档记录自动级联删除 |

**推论**：Phase E 核心（照片/人员删除）**大概率无需 schema migration**——既有 CASCADE/SET NULL 已表达级联语义；只有引入软删除才需要迁移（见 D4，建议不做）。既有 Repository 协议零删除方法（grep 实证），roadmap "Domain 协议扩 remove" 判断正确。

## 3. ADR-034 裁决点（D1–D6，每点附建议，**待 owner 拍板**）

### D1 照片删除的库级联 —— 建议确认既有 CASCADE
删照片 → 识别结果与归档记录级联删除（schema 既定）。归档记录表达"这张照片归档到哪"，照片登记消失则记录意义失效；归档产物文件本身不动（见 D3）。备选：改 SET NULL 保留归档审计行——增加复杂度，不建议。

### D2 人员删除的库级联 —— 建议确认既有 SET NULL + CASCADE
删人员 → 该人员嵌入自动删除、其识别结果保留但归属置空（变"未知人员"）、**照片全部保留**。人员是"归属维度"而非照片的容器，SET NULL 是唯一不丢照片语义的选择。

### D3 磁盘文件处置 —— 建议：DB 删登记，任何磁盘文件一律不动
照片原文件、已归档产物文件都属于用户文件系统。删除操作只删"库内登记"；需要连文件一起清理的场景不在本期（roadmap Out-of-Scope：回收站/撤销，风险另议）。UI 文案须明示"仅从库中移除登记，不删除磁盘文件"。

### D4 硬删除 vs 软删除 —— 建议硬删除（不扩 schema）
软删除（`deleted_at` 标记）需要 migration + 全查询加过滤 + 撤销语义——而 roadmap 明确 Out-of-Scope 回收站/撤销。安全网 = Phase B 启动备份（3 份滚动，已上线）。误删恢复路径：从备份还原（与 J6 演练同一流程）。

### D5 重扫对账语义（P2-2） —— 建议：扫描只增不删，失联记录显式清理
- 文件新增 → 正常登记（现有行为）；
- 文件内容变化（mtime/hash 变）→ 更新元数据 + 缩略图（本轮新增行为）；
- **文件消失 → 不自动删库记录**（防误删；如移动盘未挂载会误判）。提供独立"清理失联登记"入口（列出库内有但磁盘无的路径，用户确认后批量删登记）。

### D6 重复照片处置语义（P2-3） —— 建议：组内保留一张、其余删登记（文件不动）
在既有"检测重复"报告基础上加处置入口：每组默认保留**最早注册**一张（可切换为手动勾选保留），其余执行 D1 照片删除。原文件不动。

### 通用裁决
- 删除幂等：目标不存在 = 返回 0 行视为成功（不抛错）；
- 确认流：所有删除动作必须经确认对话框（显示级联计数预览：将删 N 张照片、M 条识别、K 条归档）；
- 权限/审计：删除走 Application UseCase，loguru 记录操作审计行（谁、何时、删了什么 id 列表）。

## 4. 实施分期与工作量

| 期 | 内容 | 交付 | 估时 |
|---|---|---|---|
| **E-1** | **ADR-034 删除断言定稿**（本计划 D1–D6 经 owner 拍板后落 `docs/development/phase8-adr-draft.md` → 定稿登记 ARCHITECTURE_DECISIONS） | ADR-034 Accepted | 0.5 天 |
| **E-2** | Domain 协议扩删：`PhotoRepository.remove(ids) -> int`、`PersonRepository.remove(id) -> int`（Recognition/Archive/Embedding 由 FK 级联覆盖，不加方法）；SQLite 实现（事务内）+ InMemory 测试替身；级联矩阵测试（每 FK 关系 × 终态断言） | 域/基础设施层删除能力 | 1.5 天 |
| **E-3** | Application 层：`DeletePhotosUseCase`（批量 + 级联预览 DTO：照片数/识别数/归档数）、`DeletePersonUseCase`（归属置空预览）、`PruneMissingPhotosUseCase`（D5 失联清理）、重复处置编排（D6）；审计日志 | 用例层 + 测试 | 2 天 |
| **E-4** | UI：照片列表多选删除入口 + 确认对话框（预览计数 + "不删除磁盘文件"明示）、人员删除入口（设置或列表）、重复报告处置按钮；全中文化（ui_text） | 用户可操作 | 1.5–2 天 |
| **E-5** | 重扫对账（D5）：扫描内容变更检测更新元数据；"清理失联登记"CLI/UI 入口 | 对账闭环 | 1 天 |
| **E-6** | 全量回归 + 用户指南补章 + 发版 **v2.4.0**（新增删除能力 = minor） | 发版 | 0.5 天 |

合计 ≈ **7–8 天**（与 roadmap 估算下限吻合）。

## 5. 测试矩阵（全量不减红线）

- 级联矩阵：删 photo → recognition_results/archive_records 清空 + 文件在盘；删 person → embeddings 清空 + recognition SET NULL + 照片保留；删 folder → photos SET NULL；
- 幂等：remove 不存在 id 返回 0；
- 批量：混合存在/不存在 id 的部分删除语义；
- 预览计数：UseCase 预览 DTO 与实际删除数一致；
- 对账：新增补齐 / 内容变更更新 / 失联保留（不自动删）/ 显式清理；
- 重复处置：保留判定正确、组内其余删登记、文件不动；
- 既有 672 用例全量不减。

## 6. 验收标准（roadmap 原文）

1. 删除照片后库与磁盘状态符合 ADR-034 语义且可审计（审计日志行 + 备份可恢复）；
2. 对账重扫不误删不漏判；
3. 全量测试不减。

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 数据破坏面大 | 硬删除 + 启动备份兜底（J6 已实证恢复可行）+ 确认对话框 + 审计日志 |
| 级联语义误解 | 本计划 §2 实证矩阵 + 级联矩阵测试锁定 |
| macOS CI 段错误复发（LIMIT-006） | 新增删除测试不含大目录压力扫描形态；复发则按既定 darwin skip 模式处置 |

## 8. Owner 裁决清单（开工前置）

- [ ] D1 确认照片删除 CASCADE（识别+归档记录随删）
- [ ] D2 确认人员删除 SET NULL + CASCADE（照片保留）
- [ ] D3 确认"磁盘文件一律不动"
- [ ] D4 确认硬删除（不扩 schema、无回收站）
- [ ] D5 确认"扫描只增不删 + 显式失联清理"
- [ ] D6 确认重复处置"保留最早注册一张，其余删登记"
- [ ] 发版版本号确认：**v2.4.0**（新增能力 = minor）
