# PhotoArchiver Documentation Audit Methodology

> **本文档是 PhotoArchiver 文档一致性审计的唯一方法论（Audit Methodology SSOT）。**
>
> 回答：**"如何做一轮轻量一致性检查？"**
>
> 迁移自废弃文档 `.ai/Consistency-Audit-2026-07-13.md` §8（2026-07-13 完整审计落地的方法论）。
>
> Version: 1.0.1 ｜ Status: Stable ｜ Last Updated: 2026-07-24

---

## 1. 适用场景

- **轻量复审**：每完成 2-3 个 Step 做一次（AI_ONBOARDING §12.1 节奏要求），不另起审计报告文档。
- **定向核查**：单一改动是否让某文档陈述失效（与 AI_ONBOARDING §12 文档触碰清单配合）。
- **全量审计**：项目级大复审（如文档体系改进），另起独立报告文档。

---

## 2. 证据采集（Evidence Collection）

| 手段 | 用途 |
|---|---|
| `read_file` | 读取 `.ai/` 根四文档 + `.ai/rules/` 全部 + `docs/` 全部 + `.ai/architecture\|business\|context\|prompts\|templates` 占位 |
| `grep` | 跨文档跑模式（如已废弃文档名、技术栈、路径、"尚未实现"等关键词） |
| 源码 introspection | `python -c` 取包的 `__all__`、`AppSettings` 字段、Schema 版本等"代码现状" |
| `bash` | `git status` / `compileall` / `pytest` 验证可运行性 |

证据必须可独立复核：每条发现至少附 2 个证据位置（文件+章节）与"实际现状"字段。

---

## 3. 比对维度（Five Dimensions）

| # | 维度 | 检查问 |
|---|---|---|
| 1 | 规则内部一致性 | 同一规则在两份文档是否两个说法？（真实矛盾） |
| 2 | 规则 vs 代码 | 规则描述与代码现状是否一致？（状态漂移：文档说"未实现"代码已实现，或反之） |
| 3 | 规则 vs docs | `.ai/rules/` 与 `docs/` + `README.md` 是否同步？ |
| 4 | 重复承载 | 同一主题在几处落正文？（SSOT 缺口，应仅一处其余指针） |
| 5 | 占位空文档 | Placeholder 是否仍 quarantine、是否在 DOCUMENT_INDEX 登记？ |

---

## 4. 严重度分级

| 级别 | 含义 | 处置 |
|---|---|---|
| **Critical / Major（真实矛盾）** | 同一规则两个说法，会误导 AI 或人类做错决策 | 当轮修复 |
| **Minor（状态漂移）** | 文档说"未实现"代码已实现，或反之 | 登记 ISSUE 或同轮修 |
| **Info（SSOT 缺口）** | 重复承载但内容一致 | 收敛改指针，可延后 |

---

## 5. 产出与登记

| 发现类型 | 去向 |
|---|---|
| 真实矛盾 | 当轮修复；无需登记（修完即没） |
| 状态漂移 | `KNOWN_ISSUES.md` 追加 ISSUE，标爆炸半径（影响哪几份文档） |
| 已解决的 ISSUE | 立即从 `KNOWN_ISSUES.md` 整条删除（不保留历史） |
| SSOT 收敛项 | 收敛动作随 Step 推进，不另起审计 |

**不另起审计报告文档**——轻量复审的产出直接落 `KNOWN_ISSUES.md`。全量审计（如本机制建设轮）才另起报告。

---

## 6. 节奏

权威节奏定义见 `.ai/AI_ONBOARDING.md` §12.1：每完成 2-3 个 Step 做一次轻量一致性检查，沿用本方法论。

---

> 📝 本文件由 AtomCode (GLM-5.2) 于 2026-07-19 迁移自 `.ai/Consistency-Audit-2026-07-13.md` §8（该文档已 Deprecated，独有信息迁此为正文 SSOT）。

End of audit-methodology.md
