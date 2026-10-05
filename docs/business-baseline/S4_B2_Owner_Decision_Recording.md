# S4-B-2 — Owner Decision Recording（裁决登记验证报告）

- 日期：2026-10-04
- 任务：Owner 裁决登记与一致性验证（Decision Recording Only）
- 结果：**OWNER-DECISION-INCOMPLETE** —— 未登记任何裁决
- 生产操作：**零**（本任务全程只读；无备份、无迁移、无重跑、无标注、无抽样、无 margin/precision 计算）
- 源码修改：**零**（本轮唯一新增即本报告）

---

## 1. Owner Decision Matrix（逐项 —— 全部为空）

任务书下发的九项裁决位全部为 `<OWNER VALUE>` 占位符。逐项核查结果：

| 决策 | 任务书下发值 | 磁盘核查 | 状态 |
|---|---|---|---|
| **D-7** face scope | `<OWNER VALUE>` | 决策矩阵 L259：`☐ APPROVE ☐ REJECT ☐ DEFER` | **缺失** |
| **C-1** migration 011 | `<OWNER VALUE>` | L260：`☐ APPROVE ☐ REJECT ☐ DEFER` | **缺失** |
| **D-1** human annotation | `<OWNER VALUE>` | L261：`☐ APPROVE ☐ REJECT ☐ DEFER` | **缺失** |
| **D-2** annotation protocol | `<OWNER VALUE>` | L262：`☐ APPROVE ☐ MODIFY ☐ DEFER` | **缺失** |
| **D-3** p / confidence / e / u / acceptable risk | 全部 `<OWNER VALUE>` | L263：`☐ values: p=__ z=__ e=__ u=__ ☐ DEFER` | **缺失** |
| **C-4** margin | `<OWNER VALUE>` | L264：`☐ DEFER ☐ BUILD ☐ REJECT` | **缺失** |
| **D-4** automatic confirmation scope | `<OWNER VALUE>` | L265：`☐ DEFER` | **缺失** |
| **D-5** post-confirmation archive behavior | `<OWNER VALUE>` | L266：`☐ DEFER` | **缺失** |

**缺失字段计数：9/9 项决策缺失（其中 D-3 展开为 5 个子值，合计 13 个必填值全空）。**

### 1.1 磁盘核查证据（为何判定"未收到裁决"而非"未找到"）

| 核查动作 | 结果 |
|---|---|
| `S4_B2_Owner_Decision_Gate.md` §10 矩阵勾选数 | `grep -c "☒\|☑"` = **0**（八行全空） |
| `docs/business-baseline/` 下裁决/裁定文件 | 仅 5 份报告（B-1 验收、B-2 Entry、D-7 Preflight、Owner Gate、Prep Blocked），**无裁决记录** |
| `docs/decisions/` | 仅 `AUD-017-person-embeddings-decision.md`（2026-09-28，与 S4-B-2 无关） |
| `git log` | HEAD 仍 `27bdc64`，无裁决提交 |
| 2026-10-03 之后新增的 `.md` | 仅本轮系列报告，无裁决文件 |

结论：**Owner 裁决未在任务书中填写，亦未以任何其他载体送达。** 按既定规则不代填、
不推断、不以 AI 建议充当裁决。

---

## 2. Validation

```text
INCOMPLETE
```

| 验证项（任务书 Decision Validation 段） | 结果 | 说明 |
|---|---|---|
| D-7 必须给出实际 face-count ranges（含现有档位 / future ranges 许可） | **无法验证** | 无值；且仅写 `APPROVE` 亦不合格 |
| D-2 必须明确双人独立性 / 覆盖范围 / 100% 仲裁 / adjudicator 身份 / re-annotation 规则 | **无法验证** | 无值 |
| D-3 五值须各带数值 + 单位 + 语义（如 `confidence` 须为 `95%` 而非 `95`） | **无法验证** | 五值全空 |
| 统计语义（unique units ≠ annotation events ≠ annotators） | **机制就绪，输入缺失** | 见 §3 |
| 跨决策一致性（C-4=DEFER ↔ 不得要求 margin strata；D-7=REJECT ↔ 不得执行放宽聚类；C-1=REJECT/DEFER ↔ 不得迁移；D-1=REJECT ↔ 不得进入人工标注） | **无法验证** | 无值即无从判定冲突 |
| 是否存在默认值推断 | **通过** | 本报告及前序全部报告均未代填任何 Owner 值 |

**语义冲突检查（INCONFLICTING-VACUOUS）**：在无任何裁决值的前提下，不存在可判定为冲突的
组合；但这**不构成通过**——空集不等于一致，故总体判定为 INCOMPLETE 而非通过。

### 2.1 可直接填写的裁决表（供 Owner 补齐；本表不含任何 AI 预填）

```text
D-7 face scope:
  裁决 = [ APPROVE | REJECT | DEFER ]
  若 APPROVE，实际 scope 档位 = [例：(1,1) (2,3) (4,5) (6,10) (11,∞) 全部五档]
  是否包含全部现有档位 = [ 是 | 否 → 列出 ]
  是否允许 future ranges（超出 (11,∞) 的新档） = [ 是 | 否 ]

C-1 migration 011（008→011）:
  裁决 = [ APPROVE | REJECT | DEFER ]
  若 APPROVE，停机窗口 = ____ ；备份保留位置 = ____

D-1 human annotation:
  裁决 = [ APPROVE | REJECT | DEFER ]

D-2 annotation protocol（逐项必填）:
  裁决 = [ APPROVE | MODIFY | DEFER ]
  双人独立标注 = [ 是 | 否 ]
  覆盖范围 = [ 全部样本 | 抽样（比例 = ____） ]
  conflict 仲裁覆盖率 = [ 100% | ____% ]
  adjudicator 身份 = [ ____（姓名/角色/是否第三方）]
  re-annotation 规则 = [ ____（分歧后是否重标、重标上限）]

D-3 statistical parameters（每值须含数值 + 单位 + 语义）:
  p（expected precision）              = ____ （语义：____）
  confidence / z                       = ____ % （z = ____）
  e（margin of error）                 = ____ （± ____ 个百分点，比例语义）
  u（expected undecidable rate）       = ____ % （预期难例比例）
  acceptable false-auto-confirm rate   = ____ % （可接受自动确认错误率）

C-4 margin:
  裁决 = [ DEFER | BUILD | REJECT ]
  若 BUILD，范围 = [ 簇心 top1/top2 margin | 其他：____ ]

D-4 automatic confirmation scope:
  裁决 = [ DEFER | 限定范围：____ ]

D-5 post-confirmation archive behavior:
  裁决 = [ DEFER | 直接归档 | 需人工确认后归档 ]
```

---

## 3. Statistical Parameters

```text
p                       = OWNER DECISION INCOMPLETE
confidence              = OWNER DECISION INCOMPLETE
z                       = OWNER DECISION INCOMPLETE
e                       = OWNER DECISION INCOMPLETE
u                       = OWNER DECISION INCOMPLETE
acceptable risk         = OWNER DECISION INCOMPLETE
```

**不输出任何数字。** 在 p/z/e/u 缺失时计算 `n0` / FPC `n` / `gross` /
`expected_effective` / `annotation_events` 必然依赖默认值推断 —— 这是任务书与前序报告
共同禁止的行为，故全部留空。

机制已就绪、仅待输入（**公式非裁决，仅为输入后的计算路径**）：

```text
unique calibration units  = 抽样的独立统计单位（Cluster）—— precision 分母单位
annotation events         = gross × annotator_count（双人制 ×2）—— 不可当作独立样本
annotators                = 独立自然人数（≥2 独立 + adjudicator 另计）

n0                  = z² · p(1−p) / e²
n                   = N · n0 / (N + n0 − 1)              （FPC 必用：N 仅 36 或 44）
gross               = min( ceil( n / (1 − u) ), N )
expected_effective  = gross × (1 − u)
annotation_events   = gross × annotator_count
```

**普查封顶规则（CP11.1）**：当 `gross = N`（总体普查）时，
`expected_effective = N × (1 − u) < n` 恒成立 —— 已达到总体普查上限，
undecidable 损失**不能再通过扩大样本消除**，必须如实报告有效分母低于理论目标。
前序实测：N=44 / e=±7% / u=20% → gross = 46 > N → 封顶为普查 44。

---

## 4. Production Gate

```text
OWNER-DECISION-INCOMPLETE
```

不得输出 `READY-FOR-PRODUCTION-PREP`。理由：13 个必填裁决值全空，其中
**C-1**（迁移授权）、**D-7**（重跑授权与实际 scope）为本任务直接消费项，
**D-3** 五值为样本量计算的必需输入。

### 4.1 跨决策一致性规则的执行状态

| 规则 | 触发条件 | 当前 | 后果 |
|---|---|---|---|
| C-4 = DEFER | 未裁决 | 未触发 | 首轮**不得**要求 margin strata |
| D-7 = REJECT | 未裁决 | 未触发 | 放宽 scope 的生产聚类**不得**进入执行 |
| C-1 = REJECT / DEFER | 未裁决 | 未触发 | 生产 migration **不得**执行 |
| D-1 = REJECT | 未裁决 | 未触发 | **不得**进入真实人工标注 |

当前所有生产动作因「无授权」而一律不执行 —— 与「因裁决为 REJECT 而不执行」是不同
性质：**本轮是授权缺失，不是裁决否决**。

---

## 5. 登记载体说明（未登记的原因与将使用的载体）

任务书要求「把最终裁决写入项目当前正式决策载体，优先复用既有规范，不创建平行格式」。
本轮**未登记**，因无任何裁决值可登记。裁决补齐后将写入：

- **裁决矩阵回填**：`docs/business-baseline/S4_B2_Owner_Decision_Gate.md` §10（勾选 + 数值）；
- **正式决策记录**：沿用既有 `docs/decisions/` 命名规范，新建一份 ADR 风格的裁决记录
  （字段：decision ID / date / owner / decision / rationale / technical evidence
  reference / scope / consequences / reversibility），与 `AUD-017-person-embeddings-decision.md`
  同目录同格式，**不另建平行载体**。

## 6. 合规声明

- 本任务**未执行任何生产动作**：无备份、无 migration、无 recognition/clustering 重跑、
  无 sampling、无 calibration annotation、无 margin/precision 计算、无自动确认/归档；
- **未修改业务代码**；本轮唯一新增文件为本报告；
- **未填写任何 Owner 裁决默认值**；
- 停止并等待 Owner 补齐 §2.1 裁决表。