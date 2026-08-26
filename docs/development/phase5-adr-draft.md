# 阶段 5 打包策略前置门草案（ISSUE-018 终局裁决：运行形态定位）

> **文档性质**：ADR 草案（Proposed 状态），阶段 5 开工前置门产出。
>
> **产出时间**：2026-08-26 ｜ **产出者**：Cline ｜ **状态**：Proposed（待评审拍板）
>
> 动议来源：KNOWN_ISSUES ISSUE-018（打包安装态不可运行）——v1.0.0 发布后首次挂账的分发预期问题。

---

## 0. 裁决点汇总（待拍板）

| # | 裁决点 | 选项 | 默认推荐 |
|---|---|---|---|
| B5-1 | 应用运行形态定位 | A. **源码/clone 为唯一受支持运行形态**（Release 资产定位为源码元数据产物并在页 body 标注）/ B. 投入安装态支持（console 入口 + alembic 资产 package_data + 用户目录默认值重构）作为 v1.1.0 特性 | **A** |
| B5-2 | ISSUE-018 终态 | A. 随 B5-1=A 按 by-design 正式关闭 / B. 保持 Open 等 B 落地 | **A** |
| B5-3 | Release 页标注执行 | owner 在 Release body 置顶标注文案（见 §4） | 立即执行（owner 一键） |

---

## 1. 背景：安装态断点全景（2026-08-26 实测证据）

| # | 断点 | 锚点 |
|---|---|---|
| E1 | wheel/sdist 均不含 `main.py`（pyproject 仅 `[tool.setuptools.packages.find] where=["src"]`，根入口不在包内） | `pyproject.toml:10-11` |
| E2 | 无 `[project.scripts]` console 入口 | pyproject 全文 grep 零命中 |
| E3 | `_ALEMBIC_CFG_PATH` 按仓库五层 parent 解析 alembic.ini；安装态指向 site-packages 上层不存在位置 → bootstrap 迁移步必失败 | `alembic_runner.py:14` |
| E4 | 插件目录按 4×parent 解析到仓库 `examples/plugins`；安装态不存在 → 插件功能静默缺失 | `main_window.py:149` |
| E5 | `DATABASE_URL`/`MODEL_PATH`/`LOG_DIRECTORY` 默认值为 CWD 相对路径 → 安装态行为随启动目录漂移 | `.env.example:19-20,16` / `settings.py` 默认值 |
| E6 | 无 MANIFEST.in、无 package-data 配置 → sdist 不含 alembic.ini/versions/main.py/resources | MANIFEST 探针零命中 |

**受支持流现状对照**：user-guide 引导的完整链路（clone → venv → `pip install -r requirements/base.txt` → `python main.py`，入口自带 src 路径注入）**全程不 pip install 包本体**——即当前唯一受支持形态本就是源码形态，与 E1-E6 无冲突。

---

## 2. 方案对比

### 方案 A：源码形态定位（推荐）

- Release 页 body 置顶标注（文案见 §4）；wheel/sdist 保留（供依赖审查与版本元数据用途），但明示不支持 `pip install` 安装态。
- ISSUE-018 以 by-design 关闭；KNOWN_ISSUES 移除条目。
- 零代码改动、零风险、与既有全部文档/测试基线一致。

### 方案 B：安装态支持（v1.1.0 特性）

需打包策略小 ADR + 至少四件工程改造：① `[project.scripts]` console 入口；② alembic.ini/versions 纳入 package_data 并将 E3 路径解析改为包相对回退；③ 插件目录改为可配置（AppSettings.plugin_dirs）；④ DATABASE_URL/MODEL_PATH/LOG 默认值迁往平台用户目录（**设置语义破坏性变更**，触及 ADR-010/022 的 base 设计）。规模中-大，且当前无非技术用户分发需求驱动。

---

## 3. 推荐 & 理由

**推荐 B5-1=A**：E1-E6 证明安装态支持不是"补一个 package_data"而是运行形态级重构；在无非技术用户分发的现实需求下投入，违背 YAGNI 且引入设置语义破坏面。方案 A 以一条标注获得确定性终态，ISSUE-018 就此终结；若未来出现真实分发需求，本草案即 B 方案的设计起点。

## 4. Release 页标注文案（B5-3 执行物料，owner 粘贴至 Release body 置顶）

```text
> ⚠️ Installation note: this project is designed to run from a source checkout.
> The attached wheel/sdist are metadata artifacts and do NOT produce a runnable
> install. Please follow docs/user-guide/installation.md:
>   git clone → venv → pip install -r requirements/base.txt → python main.py
```

## 5. 影响范围

| 文件 | 变更 |
|---|---|
| `docs/development/phase5-adr-draft.md` | 本草案（新建） |
| `.ai/DOCUMENT_INDEX.md` §2.4 | 登记本草案行 |
| `.ai/KNOWN_ISSUES.md` | B5-2=A 后移除 ISSUE-018 条目（同提交） |
| `.ai/PROJECT_STATUS.md` | §3 加 M9 行、§5 追记、Remaining/Next Step 刷新 |
| GitHub Release v1.0.0 body | owner 粘贴标注（站外动作） |
| 代码 / Schema / 依赖 | **零变更** |

## 6. 完成标准

- [ ] 三项裁决点有明确拍板记录（本文件转定稿）
- [ ] Release 页标注上线（B5-3）或明确豁免
- [ ] ISSUE-018 按 B5-2 结果终态化并同步 KNOWN_ISSUES
- [ ] DOCUMENT_INDEX / PROJECT_STATUS 同步
- [ ] 代码零变更声明成立（git diff 仅 .ai/docs）

## 7. 拍板后流转

```text
拍板 → 本文件头转定稿 → ADR-031 登记（如涉及架构决策）→ B5-3 标注执行
     → KNOWN_ISSUES ISSUE-018 终态化 → PROJECT_STATUS 刷新 → 收官
```

---

> 📝 本草案由 Cline 于 2026-08-26 产出，属阶段 5 开工前置门评审材料。