# FINAL_HEALTH_CHECK.md — PhotoArchiver 全面工程健康体检 · 最终报告（Stage 9）

- **审计周期**: 2026-09-28（Stage 0–9 单日完成，10 份分项报告 + 台账见同目录）
- **对象**: HEAD `2823d1c7ceaab09c38d39b9a80e1e724839cfa17`（main，2026-09-28）｜ 性质: READ-ONLY，业务代码零修改
- **方法**: 证据驱动分阶段审计（基线→架构→业务逻辑→数据→测试→文档→可靠性/安全/性能→UI→交叉→综合）；每条结论有 文件:行号/测试名/命令 级证据；VERIFIED/INFERRED/UNKNOWN 全程区分

---

## 1. Executive Summary

PhotoArchiver 当前是一个**工程质量高于其文档与流程治理水平**的项目。代码侧：全量测试 **1310 passed / 6 skipped / 0 failed**（本轮两次独立实测，250.55s/263.36s），行覆盖 **93.2%**（实测），ruff 与 mypy（258 文件）零告警，分层架构**零循环依赖**（AST 全图 SCC 验证），迁移链 001–008 双向幂等且经 13 项专项测试，安全面干净（危险原语零命中、模型 sha256 fail-closed、导出注入防护、原子写）。业务侧：此前 Stage F 审查判 FAIL 的 5 个代码级阻断项（BLK-1/2/3/4/5）与 2 项裁决（D-1/D-2）经本审计逐链核验**确已修复**（五点链证据 + 13 项回归）；仓库外 Stage4.2 冻结复审判定 8 项冻结条件满足。

**但项目不能据此宣布 HEALTHY**，原因集中在治理面而非代码面：

1. **SSOT 文档体系对 HEAD 全面滞后（AUD-001，唯一 P1）**——PROJECT_STATUS 七章节全部过期（仍称阶段 C–F"待立项"）、ADR/导航索引/手册/FAQ/CHANGELOG 五面同损；阶段收尾义务无书面登记载体是其根因。
2. **唯一与 HEAD 同步的业务基线（Stage1–4.2 + 冻结判定 + D-2 校准证据）完全在仓库外**、不受 git 保护（AUD-003）。
3. **44 个提交未推送**，远端 CI 未验证 HEAD 区间（AUD-002）。
4. 一个**设计级业务缺口待 owner 决策**：识别自动匹配的候选源 `person_embeddings` 全 git 历史零写入者，自动匹配永久空转（AUD-017，测试以 stub 掩蔽）。

**最终状态判定：ATTENTION**（判定依据见 §15）。

## 2. Baseline [VERIFIED]

| 项 | 值 |
|---|---|
| Version / Tag | pyproject 2.8.0；`git describe` = v2.8.0-**47**-g2823d1c（47 提交未发版） |
| HEAD / Branch | `2823d1c`（2026-09-28）/ main，**领先 origin/main 44 提交未推送**；工作树干净（审计产物除外） |
| 测试基线 | 1310 passed / 6 skipped / 0 failed（两次实测）；覆盖率 93.2%（10,363/11,115 行，实测，分母不含 main.py） |
| 工具链 | Python 3.11.9 · PySide6 6.11.1 · SQLite（裸 sqlite3 仓储 + Alembic）· insightface/onnxruntime · ruff/mypy 零告警 |
| 规模 | 源码 258 文件 28,887 行；测试 169 文件 31,530 行 |

## 3. Architecture Assessment

**实际状态（强）**：五层 + 组合根，依赖方向正确（domain 零内部依赖、application 只依赖 domain）；无模块级循环依赖；SQL/图像/AI/第三方隔离全部达标并有常驻 CI 的 AST 守卫测试；域模型非贫血（实体校验 + 聚类/配对域服务承载真实算法）。
**主要违约（治理）**：DEP §4 依赖矩阵与代码、守卫测试三方矛盾——5 行过期，最典型是矩阵禁止 `infrastructure→application` 而实际 19 处 ports 实现（端口模式本身正确，矩阵是历史快照）（AUD-009 P2）；application 层 3 处直接文件 I/O 违反 DEP §17 且守卫未编码该规则（AUD-010 P2）。
**技术债**：UseCase 协议边界双轨制（11 协议 vs 36 服务，新流程绕过）（AUD-011）；main_window 1577 行 God-class 趋势（逻辑已外移，趋势项）（AUD-013）；common/ 空置。

## 4. Business Logic Assessment

**核心链**（导入→扫描→识别→聚类→配对→审核→归档→导出）逐链深查，输入→处理→状态→数据→输出行为**正确且幂等**：

- 正确行为：八类重复操作七类有设计级幂等（TOCTOU 降级合并、content-hash 对账、run 追加不覆盖人工决定、observation 去重、(person,photo) 去重、alembic 幂等、终态跳过）；五个状态机终态封闭无非法转换；取消持久部分结果且重试只覆盖缺口（1200 张确定性回归）。
- 缺失行为：识别自动匹配空转（AUD-017 P2，owner 决策项）；配对确认→归档执行的全链贯通回归缺失（AUD-004 残余）。
- 错误行为：无功能性错误发现。归档批 FS/DB 部分失败不一致属设计权衡未声明（AUD-015 P2）；取消延迟=剩余队列排空（AUD-023 P2，机制级根因，状态一致性无损）。
- 未验证行为：真机 GUI 走查（验收脚本体系在案，owner 侧）。

## 5. Data Assessment

**Schema/Migration（强）**：11 表约束密度高（UNIQUE/CHECK/FK 全覆盖，除两处 status 列不对称）；迁移线性链、双向、幂等守护、008 回滚先回填 NULL；新库/升级库同径（Alembic 单径）；启动备份（VACUUM INTO 快照+滚动窗）+ quick_check + WAL + busy_timeout；13 项迁移/升级测试。
**一致性**：17 表全有真实读写方（无孤儿表/无读不存在列）；归档去重身份五点一致（migration→仓储→planner→executor→计数器）。
**缺口**：`person_embeddings` 零生产写入者（AUD-017 的数据面）；级联策略不一致（删人：配对历史 CASCADE vs 识别/归档 SET NULL）；`file_hash` 只写不读（AUD-018 P3 集合）。

## 6. Test Assessment

**强项**：1310 用例行为级断言、真实感高（真实 SQLite/Executor/qtbot/subprocess 进程级）；确定性生命周期套件（取消/重试/恢复）；守卫三件套常驻 CI；三次全量运行零 flaky；覆盖率 93.2% 且核心业务文件普遍 90–100%。
**盲区（按风险）**：①全链贯通回归（两段式导入→配对确认→归档执行，无单条串联测试）；②workers 任务错误/回滚分支 74.1%（AUD-019 P2）；③配对服务并发删除守卫 14 行；④模型下载失败路径；⑤darwin 4 组 skip（AR-01 在案）；⑥main.py 与 tools/ 在覆盖分母外（AUD-021 P3）。

## 7. Documentation Assessment

**SSOT 判定**：`.ai/PROJECT_STATUS.md` 是指定的唯一状态权威，但**当前不可作为决策依据**（七章节全部过期，AUD-001 P1）；现行有效的业务基线在仓库外（Stage1–4.2 已对齐 2823d1c 并判冻结条件满足）。`dependency-rules.md` §4 矩阵与守卫测试矛盾（AUD-009）。历史规划文档无历史标记（AUD-022）。README/架构总览/项目结构/rules 其余部分与实际一致。CHANGELOG 止于 2.8.0。
**根因**：阶段收尾义务（每阶段同步五类文档）无书面登记载体，六个开发会话连续未履行。

## 8. Reliability / Security / Performance

- **可靠性**：任务生命周期三层防护（身份路由/终态去重/重放幂等）成熟；崩溃恢复（备份+完整性+分片持久化）完整；缺口=取消延迟随队列排空（AUD-023 P2）与归档批 FS/DB 失败语义（AUD-015 P2）。
- **安全**：面干净——危险原语零命中、模型 sha256 fail-closed、导出公式注入防护（OWASP 口径+专项测试）、路径遍历三层防护、原子写、无密钥泄露；插件信任边界已明文声明（非沙箱、默认不装载）；依赖 CVE 未比对（记 Unknown，建议例行 pip-audit）。
- **性能**：无未声明的 O(n²)/N+1；已知取舍（候选驻留、planner 复杂度、重排 P1/P2）均有代码内声明或 owner 裁决（AR-05）；用户可感项仅取消延迟（AUD-023）。

## 9. Cross-Dimension Conflicts

十维矩阵 4 维一致、4 维已立案、2 维部分缺口（Stage 8）；跨维核对未发现台账外的新独立根因。要点：三层合谋的静默缺口（计划承诺×代码零写入×测试 stub 掩蔽 = AUD-017）；文档 X/代码 Y/守卫 Z 三方矛盾（AUD-009/014）；发布就绪度三重缺口叠加（此刻发版 = 功能零文档记载 + 未过远端 CI，AUD-001/002 交叉）。

## 10. Findings Summary

```text
P0: 0
P1: 1   AUD-001  文档 SSOT 对 HEAD 全面滞后（含收尾义务无登记载体根因）
P2: 10  AUD-002  44 提交未推送/远端 CI 未验证     AUD-003  业务基线在仓库外
        AUD-004  F1-1 全链回归缺口（部分核验后残余） AUD-009  DEP 矩阵三方矛盾
        AUD-010  application 文件 I/O 违反 §17+守卫盲区 AUD-014  Top-1 文档残留 3 载体（F1-4 未修）
        AUD-015  归档批 FS/DB 部分失败不一致        AUD-017  person_embeddings 零写入者（待 owner 决策）
        AUD-019  workers 错误路径测试缺口           AUD-023  取消延迟=剩余队列排空
P3: 15  AUD-005/006/007/008/011/012/013/016/018/020/021/022/024/025（文档重复承载、
        杂物入库、pre-commit 无配置、协议双轨制、命名混淆、结构热点、DTO 校验、
        Schema nit、契约测试名实不符、覆盖范围声明、历史文档标记、连接隐式关闭、审核空队列语义）
ACCEPTED-RISK: 5  AR-01(LIMIT-006 macOS) / AR-02(LIMIT-002 取消粒度) / AR-03(LIMIT-004) /
        AR-04(LIMIT-001) / AR-05(重排 P1/P2 不做) —— 均 owner 在案，本轮不重开
```

## 11. Risk Map

| 风险域 | 等级 | 驱动 Finding |
|---|---|---|
| 发布风险 | **高** | AUD-001+002+003 叠加：此刻发版 = 功能零文档 + 未过远端 CI + SSOT 误导 |
| 业务风险 | 中 | AUD-017：自动匹配空转（若 owner 预期"确认后同类照片自动归属"则落差实质存在）|
| 架构风险 | 中 | AUD-009/010：治理文档失真误导后续开发决策 |
| 测试风险 | 中 | AUD-019 + AUD-004 残余：错误路径与段间接缝无回归网 |
| 数据风险 | 低-中 | AUD-015：崩溃窗口 FS/DB 分歧（低概率、高困惑）；AUD-018①级联不一致 |
| 维护风险 | 低-中 | AUD-013 main_window 趋势；AUD-011 协议双轨；AUD-006 杂物 |
| 安全风险 | 低 | 面干净；仅 CVE 未比对为 Unknown |
| 性能风险 | 低 | AUD-023 取消延迟为唯一用户可感项；其余在案可接受 |

## 12. Technical Debt

- **明确债务（应还）**：文档五面滞后（AUD-001）；DEP 矩阵过期（AUD-009）；Top-1 残留 3 载体（AUD-014）；杂物入库 + pre-commit 无配置（AUD-006/007）；历史文档标记（AUD-022）。
- **潜在债务（需决策后定性）**：person_embeddings 死路径（AUD-017，实现样本化 or 登记限制）；归档批 FS/DB 语义（AUD-015，补对账 or 文档声明取舍）；协议双轨制（AUD-011，补协议 or 废除协议层）。
- **可接受复杂度（有据不动）**：per-call 连接 refcount 关闭（CPython 钉定）；候选驻留/planner 复杂度（代码内声明）；main_window 规模（逻辑已外移）；LIMIT-001/002/004/006（AR 在案）。
- **必须治理**：AUD-001（任何发版/冻结签核前）；AUD-017 决策（冻结签核前）。

## 13. Unknowns

1. 远端 CI 对 HEAD 区间的验证状态（44 提交未推送，本地不可证）。
2. `%LOCALAPPDATA%` 生产库实态（迁移版本/数据规模）与升级演练。
3. v2.8.0 安装包二轮真机验收是否已执行（PROJECT_STATUS 记为待 owner，此后无记录）。
4. `D:\workFile\photo-archiver\` PRD 文档集（2026-07-01）与仓库现状的偏离度。
5. 依赖 CVE 面貌（未做 pip-audit）。
6. Stage-F FAIL 判定的 §1–§18 审查报告原文（未落盘，仅会话存在 + 核验记录间接引用）。

## 14. Recommended Next Actions（不直接修改项目；均为建议）

| Priority | Action | Reason | Affected Area | Dependency | Expected Outcome |
|---|---|---|---|---|---|
| **1** | 以仓库外 Stage1–4.2 为源回填仓库内五文档：PROJECT_STATUS（含迁移链 001–008）、KNOWN_ISSUES（合并重复表）、ARCHITECTURE_DECISIONS（补 E-SG-6/D-3/inclusive/BLK 系 ADR）、DOCUMENT_INDEX、CHANGELOG（Unreleased 段收 47 提交） | AUD-001 P1；SSOT 失真误导一切后续决策 | .ai/ + CHANGELOG | owner 授权文档轮 | 状态文档与 2823d1c 一致，恢复决策可信度 |
| **2** | 把 Stage1–4.2 六份业务基线文档收入仓库（docs/business-baseline/）并纳入 git | AUD-003 P2；唯一现行基线不受版本保护 | docs/ | Action 1 | 基线受 git 管理，冻结判定可追溯 |
| **3** | Owner 三项裁决：①AUD-017 样本化匹配（实现 or 登记接受限制）；②AUD-015 归档崩溃对账（补工具 or 文档声明取舍）；③是否推送 44 提交过远端 CI 后发版 | 三者均为"代码正确但需业务定性"的决策点 | 业务/发布 | 无 | 缺口定性，冻结签核前置条件闭合 |
| **4** | 修复 AUD-014 三载体（archive_planner docstring + 两文档）+ 更新 DEP §4 矩阵对齐守卫测试（AUD-009） | 纯文档/注释修正，机械且低险 | 文档 | 无 | 消除文档-代码-守卫三方矛盾 |
| **5** | 补测试：全链贯通回归（导入→配对确认→归档执行单条）+ workers 错误分支 + 配对守卫分支 | AUD-004 残余 + AUD-019 P2 | tests/ | 无 | 段间接缝与失败路径有回归网 |
| **6** | 取消延迟修复评估：`shutdown(cancel_futures=True)` + 批量 future.cancel（或任务体感知取消） | AUD-023 P2；机制级根因已定位 | run_recognition/match 服务 | owner 立项 | 取消延迟降至秒级 |
| **7** | 卫生批次：删除入库杂物（AUD-006）、补 pre-commit 配置或移除声明（AUD-007）、conflict_strategy 命令层校验（AUD-016）、审核空队列 vs 读失败区分（AUD-025）、历史文档标记（AUD-022） | P3 批量清偿 | 多点 | 无 | P3 清零 |
| **8** | 发布前例行：`pip-audit` + 真机验收按 ui-acceptance-script 执行 | Unknown 收敛 | 发布流程 | Action 1–3 | Unknowns 面收敛 |

## 15. 最终健康状态

```text
╔══════════════════════════════════════════════════╗
║            最终状态：ATTENTION                    ║
╠══════════════════════════════════════════════════╣
║ 代码与测试面：HEALTHY                             ║
║ 治理与发布面：HIGH-RISK（若此刻发版/签核冻结）    ║
╚══════════════════════════════════════════════════╝
```

**判定依据**——该状态由以下已确认 Finding 导致，缺一即升/降级：

- **未判 HIGH-RISK / CRITICAL**：P0=0；无数据损坏/丢失/安全越界/核心业务不可用证据；核心链行为正确且幂等（Stage 2/3 深查）；1310 测试两跑全绿 + 93.2% 覆盖（Stage 4 实测）；此前判 FAIL 的代码级阻断项经独立核验确已修复（Stage 2）。
- **未判 HEALTHY**：AUD-001（P1）使 SSOT 状态文档在阶段 C–F 期间**整体失真**，按项目自身方法论属"会误导决策的真实矛盾"；AUD-002/003 使"代码已验证、基线受保护、交付有记载"三个发布前提同时不成立；AUD-017 为冻结基线内未定性的业务缺口。以上任一项不解决，"可继续开发"成立而"可发布/可签核冻结"不成立。
- **升级触发器**：若 owner 决定近期发版或签核冻结 → 治理面缺口（AUD-001/002/003/017）叠加后整体状态应按 **HIGH-RISK** 对待；若完成建议 Action 1–3 → 整体状态可升 **HEALTHY**（代码面本已达标）。

---

> 审计产物索引：AUDIT_BASELINE / ARCHITECTURE_AUDIT / CODE_LOGIC_AUDIT / DATA_PERSISTENCE_AUDIT / TEST_QUALITY_AUDIT / DOCUMENTATION_AUDIT / RELIABILITY_SECURITY_PERFORMANCE_AUDIT / UI_AUDIT / CROSS_DIMENSION_RECONCILIATION / FINDINGS_LEDGER（+ evidence/ 可复现证据）。全程 READ-ONLY，业务代码零修改，未提交任何文件。
