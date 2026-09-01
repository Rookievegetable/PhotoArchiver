# PhotoArchiver — Phase 9 Filter Completeness 实施结果报告

> **文档性质**：Phase 9 P0（FEAT-P9-1/2/3）实施结果报告
> **产出时间**：2026-09-02
> **授权**：Owner「PHASE 9 — FILTER COMPLETENESS / P0 IMPLEMENTATION AUTHORIZATION」
> **基线**：HEAD `4c0cc8c`（== origin/main，clean）
> **结论**：**PHASE 9 P0 FILTER COMPLETENESS — COMPLETE**（DoD 23/23；P1/P2 未启动，STOP）

---

## 1. Scope

仅实施授权的三个 P0 Feature：日期范围筛选（FEAT-P9-1）、人员筛选（FEAT-P9-2）、三轴联合筛选 + FILTERED 导出联测（FEAT-P9-3）。P1 CLI 与 P2 项（删除/重复处置、CURRENT_BATCH、分发）未触碰。

## 2. Implemented Features

| Feature | 实现要点 |
|---|---|
| FEAT-P9-1 日期轴 | FilterBar From/To 各由 checkbox 门控（原占位注释自述的设计："启用需可勾选开关"）：未勾选 = 该轴显式无约束（QDateTimeEdit 恒有值，门控即"未设置"表示）；勾选后取控件值进入 criteria；`from > to` 原样透传（仓储区间语义诚实返回空，不 clamp 不拒绝）；`_emit_criteria` 保持唯一 None 判定点，`clear()` 复位全轴 |
| FEAT-P9-2 人员轴 | 新增薄读取用例 `ListPersonsService`（复用 `PersonRepository.list_all`，SearchPhotosService 先例；Presentation 不触仓储——DEP-003/004）；MainWindow 构建末尾填充 + `import_people` 完成后重填（`_on_completed` 按 task_name 钩住）；`set_persons` 重填时阻塞信号（单次收尾 emit、无逐项伪发射）、保留仍在册的当前选择、否则复位 "All persons"；选中经 `PhotoSearchCriteria.person_id` 走既有 `search()` JOIN 语义（零重实现） |
| FEAT-P9-3 联合 + 联测 | 真实 SQLite AND 语义全组合矩阵 + 真实 UI 链 FILTERED 导出联测（见 §6）；另修复联测暴露的 QVariant userData 缺陷（见 §4） |

## 3. Files Changed

| Commit | 文件 |
|---|---|
| `d731b17` feat(filter): enable date range filtering | `filter_bar.py`（日期轴）、`tests/unit/presentation/test_filter_bar.py`（新增 9 测试） |
| `4d077fa` feat(filter): enable person filtering | `filter_bar.py`（人员轴）、`application/services/list_persons_service.py`（新增）、`application/__init__.py`、`application/services/__init__.py`、`app/services.py`（装配）、`main_window.py`（填充/重填接线）、`test_filter_bar.py`（+8）、`tests/unit/application/test_list_persons_service.py`（新增 2） |
| `87f43e5` test(export): cover combined filter criteria | `filter_bar.py`（QVariant 修复，见 §4）、`tests/integration/test_filter_criteria_combinations.py`（新增 10）、`tests/integration/export/test_filtered_export_combined_criteria.py`（新增 7）、`test_filter_bar.py`（userData 断言同步） |
| `<docs commit>` 交付物 | 本报告 + `docs/roadmap/NEXT_PHASE_FEATURE_DEVELOPMENT_PLAN.md` |

生产代码净变化：`filter_bar.py`（重写日期/人员轴接线）、`list_persons_service.py`（新增 47 行薄服务）、`app/services.py`（+3 行装配）、`main_window.py`（+18 行接线）、两个 `__init__.py`（导出）。**零 schema/migration/依赖/契约/规则改动。**

## 4. Implementation Notes（联测暴露并修复的缺陷）

**QVariant identity 陷阱**：初版 `set_persons` 以 UUID 对象作 combo userData，17 个 widget 单测全绿（复用了同一 Python 对象），但真实 UI 链联测中 `findData` 对"等值但不同实例"的 UUID 返回 -1（PySide6 QVariant 按包装指针比较），选中看似生效实则发射了无约束 criteria（`_current_criteria` 为 None）。修复：userData 改存**字符串 id**，`_emit_criteria` 转回 UUID；缺陷与修法均已文档化在 `set_persons` docstring。该缺陷由"真实链路优先"的测试策略直接暴露，验证了授权 §九的联测要求。

**接线顺序**：初始人员填充必须位于 `_create_photo_list` 末尾——`set_persons` 会重发 criteria，触发的列表刷新依赖已存在的 `_photo_list_model`（首版实现曾触发 smoke 测试 AttributeError，已修正并留注释）。

## 5. Tests

| 层 | 文件 | 数量 | 覆盖 |
|---|---|---|---|
| Widget 单测 | `test_filter_bar.py` | 17 | 日期门控 9（默认无约束/from-only/to-only/双界/from>to 透传/与 status 组合/门控启用/全复位/实时重发）+ 人员轴 8（初始态/填充与选择/空人员库/单次发射/选择保留/选择失效复位/三轴组合/clear 含人员轴） |
| Application 单测 | `test_list_persons_service.py` | 2 | 全目录返回（生产 InMemoryPersonRepository）/空目录 |
| 真实 SQLite 组合矩阵 | `test_filter_criteria_combinations.py` | 10 | 空/三单轴/三双轴/三轴/无命中/from>to/边界日期含端点；AND 语义逐组合精确断言 |
| FILTERED 导出联测 | `test_filtered_export_combined_criteria.py` | 7 | status-only（CSV）/person-only（CSV）/date-only（XLSX）/person+date（CSV）/三轴（CSV）/无命中（header-only）/连续两次导出无 stale criteria；真实 FilterBar→hold point→Controller→Executor→Task→Service→search→Exporter→文件，逐项泄漏矩阵断言 |

新增测试合计 **36**（534 → 570）。全部真实 SQLite / 真实链路；边界 double 仅限既有模态 Dialog/QMessageBox 策略。

## 6. Export Integration Verification

`test_filtered_export_combined_criteria.py` 六场景 + stale 防护全过，关键断言：

- 命中照片出现在 photos 区段；非命中照片的 photo/match/person/archive 四轴行**零泄漏**（泄漏矩阵逐项断言，如 person-only 场景 `"Alice" not in flat_cells`、date-only 场景 2023 照片 id 不在 workbook）。
- `dialog.active_criteria is window._current_criteria`（F5 转发不变量在联测中保持）。
- matches 区段维持契约 §3/F4 全状态语义（主集全部识别结果，status 轴已在主集生效）。
- 无命中 → header-only 文件（诚实空集）；连续两次导出 → 第二次仅含新条件主集（无跨次泄漏）。

## 7. Contract Impact

**零契约变更**：`PhotoSearchCriteria` VO、`PhotoRepository.search` SQL、Export contract、schema/migration（Alembic 001+002）、依赖清单、`.ai/rules` 全部未动（`git diff 4c0cc8c..HEAD -- alembic requirements* pyproject.toml .ai/rules` 为空）。新增 `ListPersonsService` 为 application 层薄读取用例（规则 IN-SCOPE 先例模式）。

## 8. Architecture Impact

分层边界保持：Presentation（FilterBar/MainWindow）→ Application（ListPersons/SearchPhotos）→ Domain（VO/Protocol）→ Infrastructure（SQLite）。无新依赖、无边界变更、无需 ADR。发现的**存量**问题（见 §9）不属本阶段。

## 9. Known Limitations / Observations

1. **F-002**（match controller 线程池时序 flake）：本轮全量复现 1 次，单跑 ×2 稳定（1.84s / 1.78s）——与 Phase 4.2/5/6/7 历史记录同一特征，维持 Known limitation，未修复。
2. **存量测试隔离观察**（非本阶段引入）：特定子集顺序（`test_archive_controller` + `test_export_controller*` 后紧接首个构造 MainWindow 的测试）会触发 Qt 原生级崩溃（exit 127，无 Python traceback）；经 `git stash` 在干净基线复现——**先于 Phase 9 存在**。全量套件（完整收集顺序）不受影响（570 passed）。登记为后续轮候审项，不在 P0 范围内处理。
3. LIMIT-001 / LIMIT-002 维持既有登记。

## 10. Final Status — Definition of Done（23/23）

```text
[x] Date filter enabled            [x] Person filter enabled          [x] Status regression passed
[x] Date filter tested             [x] Person filter tested           [x] Date+Person AND tested
[x] Date+Person+Status tested      [x] Empty criteria tested          [x] No-match behavior tested
[x] Real SQLite integration passed [x] FILTERED export linkage passed [x] CSV verified
[x] XLSX verified                 [x] pytest passed (570 passed / 3 skipped / 1 = F-002 已知 flake)
[x] ruff passed                    [x] mypy passed (171 files)        [x] pip check passed
[x] git diff reviewed              [x] no schema changes              [x] no migration changes
[x] no dependency changes          [x] no .ai/rules changes           [x] no unrelated refactor
```

## 11. Git Commits

```text
<docs>   docs(roadmap): add next phase plan and Phase 9 filter completeness report
87f43e5 test(export): cover combined filter criteria            (FEAT-P9-3 + QVariant 修复)
4d077fa feat(filter): enable person filtering                    (FEAT-P9-2)
d731b17 feat(filter): enable date range filtering                (FEAT-P9-1)
4c0cc8c (baseline)
```

**PHASE 9 P0 FILTER COMPLETENESS — COMPLETE**；未进入 P1 CLI / P2 项；未 push；STOP 等待 Owner 下一条授权。
