# 导入人员 业务逻辑分析（配合验收问题排查）

> 背景：UI/UX 验收第 2 项发现"成功导入内容，但导入的内容格式错误，将多个人名识别为一个人"。
> 本文详细解释导入人员的完整实现逻辑并附带关键步骤源码，末节给出与该现象的对照分析。
> **本文仅为现状分析，不含任何代码修改。** 基线：`30dedd2`（2026-09-19）。

---

## 1. 业务流程总览

```text
用户点「导入人员」
  → MainWindow._on_import_clicked()        文件选择框（txt/csv/xlsx/xlsm）
  → ImportPeopleController.import_from()   构造命令、提交后台 Worker
  → ImportPeopleTask（Worker 线程执行）
  → ImportPeopleService.execute()          Application 层用例编排
      → DispatchingPersonImportReader.read()   按扩展名分派解析器
          → ExcelPersonImportReader / TxtPersonImportReader
      → import_rows()                      分批（500 行/批）原子落库
          → Person 实体校验 → PersonRepository.add()
  → completed 信号 → 状态栏显示导入结果（导入 N / 跳过 M / 错误明细）
```

分层归属：Presentation（选文件、提交任务、显示结果）→ Application（用例编排、批
量事务）→ Infrastructure（Excel/TXT 解析器、SQLite 仓储）。UI 全程不触碰仓储。

---

## 2. 关键步骤源码解析

### 2.1 UI 入口：选文件并提交任务

`presentation/views/main_window.py`：

```python
def _on_import_clicked(self) -> None:
    """Open a file picker and start the people-import workflow."""
    path, _ = QFileDialog.getOpenFileName(
        self, DIALOG_SELECT_PEOPLE_FILE, "", PEOPLE_FILE_FILTER
    )
    if not path:
        return
    self._progress.setValue(0)
    self._status_label.setText(STATUS_IMPORTING_FILE.format(path=path))
    runnable = self._import_controller.import_from(Path(path))
    self._connect_task_signals(runnable)
```

要点：**用户选择什么文件，就用什么文件**。窗口不做任何格式预检，格式约束全部
落在解析器与实体校验层。

### 2.2 控制器：构造命令并提交 Worker

`presentation/controllers/import_people_controller.py`：

```python
def import_from(self, source_path: Path, has_header: bool = True,
                sheet_name: str | None = None):
    command = ImportPeopleCommand(
        source_path=source_path,
        has_header=has_header,        # 默认 True：首行视为表头并跳过
        sheet_name=sheet_name,        # 默认 None：Excel 取活动工作表
    )
    task = ImportPeopleTask(self._use_case, command)
    return self._executor.submit(task)
```

注意两个隐含契约：`has_header` 恒为 `True`（UI 没有暴露开关），`sheet_name`
恒为 `None`（读活动工作表）。

### 2.3 解析器分派：按扩展名路由

`infrastructure/importers/dispatching_person_import_reader.py`：

```python
_EXCEL_SUFFIXES = frozenset({".xlsx", ".xlsm"})

def read(self, source_path, *, has_header=True, sheet_name=None):
    reader = (
        self._excel_reader
        if Path(source_path).suffix.lower() in _EXCEL_SUFFIXES
        else self._text_reader      # 其余一切扩展名（含 .txt/.csv）走文本解析
    )
    return reader.read(source_path, has_header=has_header, sheet_name=sheet_name)
```

`.xls`（老二进制格式）**故意不支持**——openpyxl 无法读取，选择器已不再提供该扩展名。

### 2.4 行解析：一行 = 一个人，前四列固定语义

**这是理解验收问题 1 的核心。** 两种解析器的列语义完全一致：

`infrastructure/importers/excel_person_import_reader.py`：

```python
for row_number, cells in enumerate(worksheet.iter_rows(values_only=True), start=1):
    values = list(cells)
    if has_header and row_number == 1:
        continue                      # 首行永远按表头跳过
    if self._is_blank_row(values):
        continue                      # 空行跳过
    rows.append(self._build_row(values, row_number))

@classmethod
def _build_row(cls, values, row_number) -> PersonImportRow:
    padded_values = [cls._normalize_cell(value) for value in values[:4]]
    padded_values.extend([None] * (4 - len(padded_values)))
    name, identity, department, note = padded_values   # ← 前 4 列固定语义
    return PersonImportRow(name=name or "", identity=identity,
                           department=department, note=note, row_number=row_number)
```

`infrastructure/importers/txt_person_import_reader.py`：

```python
def __init__(self, *, delimiter: str = ",", encoding: str = "utf-8-sig") -> None:
    self._delimiter = delimiter          # 仅英文半角逗号
    self._encoding = encoding            # utf-8-sig（兼容带 BOM 的文件）

...
reader = csv.reader(file, delimiter=self._delimiter)
for row_number, columns in enumerate(reader, start=1):
    if has_header and row_number == 1:
        continue
    ...
    padded_columns = [column.strip() for column in columns[:4]]
    name, identity, department, note = padded_columns   # ← 同样前 4 列
```

**列语义表（Excel 与 TXT/CSV 一致）：**

| 列序 | 字段 | 必填 | 说明 |
|---|---|---|---|
| 第 1 列 | 姓名 `name` | 必填 | 空白 → 该行报错（见 2.6），不会中断整批 |
| 第 2 列 | 身份标识 `identity` | 可选 | 唯一标识（如工号）；用于跨文件查重 |
| 第 3 列 | 部门 `department` | 可选 | 参与无 identity 时的查重键 |
| 第 4 列 | 备注 `note` | 可选 | — |

**每一行只产生一个人**；第 1 列之外的任何内容都只可能落进 identity/department/note，
绝不会被拆分成多个人。解析器不做任何"分隔符内再切分"。

### 2.5 用例编排：分批原子落库 + 两种查重

`application/services/import_people_service.py`：

```python
BATCH_SIZE = 500

def execute(self, command: ImportPeopleCommand) -> ImportPeopleResult:
    rows = self._reader.read(command.source_path,
                             has_header=command.has_header,
                             sheet_name=command.sheet_name)
    return self.import_rows(rows)

def import_rows(self, rows) -> ImportPeopleResult:
    for batch in self._chunk_rows(rows):          # 500 行一批
        if self._unit_of_work is not None:
            with self._unit_of_work:              # 批内原子：崩溃只回滚当前批
                batch_ids, batch_errors, batch_skipped = self._import_batch(batch)
        ...
```

每行的落库决策（同文件 `_import_batch`）：

```python
identity = self._build_identity(row)              # 第 2 列非空 → PersonIdentity
if identity is not None:
    if self._repository.find_by_identity(identity) is not None:
        skipped_count += 1                        # 已有同 identity → 跳过
        continue
elif self._is_name_department_duplicate(row):     # 无 identity → 按(姓名,部门)查重
    skipped_count += 1
    continue

person = Person(name=row.name, identity=identity,
                department=row.department, note=row.note)
self._repository.add(person)
```

行级错误隔离：单行 `ValueError/ValidationError` 只记入 `errors`（带行号），
不会中断整批；只有非行级的意外异常才回滚当前批并向上传播。

### 2.6 实体校验：姓名归一化

`domain/entities/person.py`：

```python
def __post_init__(self) -> None:
    normalized_name = self.name.strip()
    if not normalized_name:
        raise ValidationError("Person name must not be empty")
    self.name = normalized_name          # 仅去首尾空白，不做任何内部切分/替换
```

姓名的归一化只有 `strip()`——**姓名内部的逗号、分号、空格、全角标点全部原样保留**。

### 2.7 导入完成的用户反馈

任务完成态经 `completed` 信号回到窗口，状态栏显示 `ImportPeopleResult`
（导入 N、跳过 M），行级错误逐条展示。用户看到"导入成功"只代表**行被接受**，
不代表格式符合预期——格式歧义（见下节）在导入侧永远是合法的"一个人名"。

---

## 3. 与验收现象"多个人名识别为一个人"的对照分析

结合上述实现，"多个人名变成一个人"必然发生在**源文件的行组织方式**上，
程序不存在把一行拆成多人的逻辑。典型成因按可能性排序：

| # | 成因 | 例子 | 结果 |
|---|---|---|---|
| 1 | **多个名字写在同一个单元格/同一行第一列** | Excel A2=`张三,李四,王五` | 一个人名为 `张三,李四,王五` |
| 2 | TXT 一行内用**中文逗号/分号/顿号**分隔 | `张三，李四，王五` | 解析器只认英文半角 `,`，整行成为一个人名 |
| 3 | TXT 一行内用**空格**分隔 | `张三 李四 王五` | csv.reader 不断行，整行成为一个人名 |
| 4 | 名单整列粘贴进一个单元格 | — | 一个单元格值 = 一个人名 |
| 5 | 第一列写了姓名、第二列又写了另一个人的姓名 | `张三,李四` | 张三为姓名，**李四被当成 identity（第 2 列）** |

**正确的名单格式**（与 `docs/user-guide/manual.md` 一致）：

```text
姓名,工号,部门,备注        ← 首行表头（必须，因为 has_header 恒为 True）
张三,E001,工程部,
李四,E002,工程部,
王五,E003,市场部,
```

- Excel：第 1 行表头，**每人一行**，A 列姓名；
- TXT/CSV：英文半角逗号分隔，UTF-8（带不带 BOM 均可），每人一行。

**建议的自查方法**（不改代码）：打开导入后的照片墙人员筛选下拉（或"删除人员"
对话框的下拉），看人员列表里是否出现"张三,李四,王五"这类**含分隔符的长名字**
——出现即证实成因 1/2/3。导入时的行级错误与跳过数也会显示在状态栏。

---

## 4. 实证更新（2026-09-20，依据人工验收会话数据库只读检查）

§3 的成因 1 已由数据库证实。导入后 `people` 表恰为 **9 行**，内容如：

```text
1曹徽文、2曹紫夏、3贾偌涵、4孙嘉岳、5吴宇琛、6王熠辰、7张宸源
2组
1赵文槿、2高奕宸、3王浴苏、4郭一墨、5寸映辰、6王语汐、7梁书祎
3组
...
```

即：名单文件把**一整组人的名字用顿号串在同一个单元格里**（§3 成因 1/4），
且组名（"2组"等）单独成行被当成了人员。程序按"一行一人"语义原样接受，
导入侧无任何告警——格式歧义在当前实现下是合法输入。改进方向（供立项参考）：
导入预览/确认页展示解析结果；单元格内出现顿号/分号分隔的多段文本时给出
"疑似多人名"警告或自动拆分；形如"N组"的行提示确认。

## 5. 相关文件索引

| 职责 | 文件 |
|---|---|
| UI 入口 | `src/photo_archiver/presentation/views/main_window.py`（`_on_import_clicked`） |
| 控制器 | `src/photo_archiver/presentation/controllers/import_people_controller.py` |
| 用例编排 | `src/photo_archiver/application/services/import_people_service.py` |
| 解析分派 | `src/photo_archiver/infrastructure/importers/dispatching_person_import_reader.py` |
| Excel 解析 | `src/photo_archiver/infrastructure/importers/excel_person_import_reader.py` |
| TXT/CSV 解析 | `src/photo_archiver/infrastructure/importers/txt_person_import_reader.py` |
| 实体校验 | `src/photo_archiver/domain/entities/person.py` |
| 行模型 | `src/photo_archiver/application/dtos/person_import.py`（`PersonImportRow`） |

排查时配合日志：`ListPersonsService: N person(s) available for filtering`
（INFO 级，每次打开筛选/删除人员都会打印当时库内人数）。
