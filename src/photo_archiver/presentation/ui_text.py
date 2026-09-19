"""用户可见文案表（ui-rules §24 Internationalization）.

Presentation 层所有面向用户的文本统一在此定义为常量——单一翻译置换点，
视图代码不散落硬编码字符串。键名按视图分组；带占位的模板用 ``str.format``。

约定：
- 任务名（WorkerTask.name，如 ``import_people``）是逻辑标识符，保持英文不动；
  用户可见的任务标签经 :func:`task_label` 映射为中文（``TASK_LABELS``）。
- 域/应用层契约文本（异常 message、枚举值、conflict strategy 值等）不在本表——
  它们是契约，不是 UI 文案。
- Window 标题保留产品名 ``PhotoArchiver``。
"""

from __future__ import annotations

# ---- 主窗口 · 工具栏 ----
MAIN_WINDOW_TITLE = "PhotoArchiver"
ACTION_IMPORT_PEOPLE = "导入人员"
ACTION_SCAN_FOLDER = "扫描文件夹"
ACTION_REVIEW_PENDING = "审核待处理"
ACTION_ARCHIVE = "归档"
ACTION_RUN_FACE_RECOGNITION = "运行人脸识别"
ACTION_EXPORT_DATA = "导出数据"
ACTION_DETECT_DUPLICATES = "检测重复"
ACTION_SETTINGS = "设置"
ACTION_CANCEL_TASK = "取消任务"

# ---- 主窗口 · 任务状态 ----
# WorkerTask.name（逻辑标识）→ 用户可见任务标签。
TASK_LABELS = {
    "import_people": "人员导入",
    "scan_and_register_photos": "扫描",
    "match_persons": "人脸识别",
    "archive_photos": "归档",
    "export": "导出",
}
STATUS_READY = "就绪"
STATUS_TASK_STARTED = "{label}已开始"
STATUS_TASK_COMPLETED = "{label}完成"
STATUS_TASK_FAILED = "{label}失败。"
STATUS_TASK_CANCELLED = "{label}已取消。"
STATUS_CANCELLING = "正在请求取消；当前处理单元完成后停止，已完成部分会保留"
STATUS_CANCEL_FAILED = "取消请求未能发送；任务仍在运行，可重试。详情请查看日志。"
STATUS_TASK_BUSY = "{label}正在进行，请等待当前操作结束后重试。"
STATUS_TASK_PREPARING = "正在准备{label}…"
STATUS_PROGRESS_UNKNOWN = "总数未知"
STATUS_TASK_PROGRESS = "{label} · {progress} · {message}"
STATUS_TASK_CANCEL_PROGRESS = "{status} · {cancellation}"
STATUS_OPERATION_FAILED = "操作未能启动：{detail}"
STATUS_REFRESH_FAILED = "页面刷新失败，请稍后重试；详情请查看日志。"
STATUS_PENDING_REVIEW_COUNT = "{count} 条识别结果待审核"

# ---- 主窗口 · 对话框与流程提示 ----
DIALOG_SELECT_PHOTO_FOLDER = "选择照片文件夹"
DIALOG_SELECT_PEOPLE_FILE = "选择人员文件"
PEOPLE_FILE_FILTER = "人员文件 (*.txt *.csv *.xlsx *.xlsm)"
STATUS_SCANNING_FOLDER = "正在扫描 {folder} …"
STATUS_IMPORTING_FILE = "正在导入 {path} …"
STATUS_ARCHIVING = "正在归档…"
STATUS_EXPORTING = "正在导出…"
STATUS_SCAN_UNAVAILABLE = "扫描不可用。"
STATUS_SCAN_ENUMERATION_FAILED = "扫描目录枚举失败：{detail}"
STATUS_MATCH_UNAVAILABLE = "人脸识别不可用。"

# 归档前置警告
ARCHIVE_DIALOG_TITLE = "归档"
ARCHIVE_ROOT_NOT_CONFIGURED = (
    "未配置归档根目录（ARCHIVE_ROOT）。请在 .env 中设置，或使用 CLI --archive-root 参数。"
)
ARCHIVE_NOTHING_TO_ARCHIVE = (
    "没有可归档的照片（跳过 {skipped} 项）。请先通过「审核待处理」确认识别结果。"
)

# 插件动作渲染
PLUGIN_ERROR_TITLE = "插件错误"
PLUGIN_ACTION_FAILED = "插件动作「{action_id}」执行失败，详情请查看日志。"
PLUGIN_RESULT_TITLE = "插件：{action_id}"
PLUGIN_FAILURE_NO_DETAIL = "动作执行失败（未提供详细信息）。"

# ---- 筛选栏（FilterBar） ----
# 占位语义：下拉列表只含真实选项；未选中任何项（currentIndex == -1）时
# 闭合框内以灰色占位文字提示"该轴不设约束"。
FILTER_PERSON_LABEL = "人员："
FILTER_ALL_PERSONS = "全部人员"
FILTER_PERSON_TOOLTIP = "按匹配的人员筛选照片；支持输入关键字即时搜索（如输入一个字即列出包含该字的人员）；未选择时显示全部。"
FILTER_STATUS_LABEL = "状态："
FILTER_STATUS_ALL = "全部"
FILTER_STATUS_PLACEHOLDER_TOOLTIP = "未选择时显示全部审核状态。"
FILTER_STATUS_PENDING = "待审核"
FILTER_STATUS_APPROVED = "已通过"
FILTER_STATUS_REJECTED = "已拒绝"
FILTER_STATUS_UNMATCHED = "未匹配"
FILTER_FROM_TOOLTIP = "筛选捕获时间晚于此时刻（含）的照片。"
FILTER_TO_TOOLTIP = "筛选捕获时间早于此时刻（含）的照片。"
FILTER_CLEAR_BUTTON = "清除"

# ---- 筛选栏 · 时间模式与摘要（Batch 4） ----
FILTER_TIME_LABEL = "时间："
FILTER_TIME_ALL = "全部时间"
FILTER_TIME_CUSTOM = "自定义时间"
FILTER_DATE_RANGE_INVALID = "开始时间晚于结束时间，已暂停筛选；请修正后再试。"
FILTER_SUMMARY_NONE = "未启用筛选"
FILTER_SUMMARY_PERSON = "人员：{name}"
FILTER_SUMMARY_STATUS = "状态：{name}"
FILTER_SUMMARY_TIME_FROM = "拍摄自 {date}"
FILTER_SUMMARY_TIME_TO = "拍摄至 {date}"
FILTER_SUMMARY_SEPARATOR = " · "
FILTER_RESULT_COUNT = "{count} 张照片"
FILTER_DATE_FORMAT = "%Y-%m-%d"

# ---- 照片库 · 空态三态（Batch 4） ----
PHOTO_EMPTY_LIBRARY_TITLE = "库中还没有照片——扫描照片目录后，照片会出现在这里。"
PHOTO_EMPTY_LIBRARY_ACTION = "扫描照片"
PHOTO_EMPTY_FILTERED_TITLE = "没有照片符合当前筛选条件。"
PHOTO_EMPTY_FILTERED_ACTION = "清除筛选"
PHOTO_EMPTY_BUSY = "任务进行中；完成后照片墙将按当前筛选自动刷新。"

# ---- 照片库 · 选择态批量操作栏（Batch 4） ----
BULK_ARCHIVE_BUTTON = "归档所选（{count}）"
BULK_DELETE_BUTTON = "移除登记（{count}）"

# ---- 照片详情对话框（Batch 4） ----
PHOTO_DETAIL_TITLE = "照片详情"
PHOTO_DETAIL_NAME = "文件名：{name}"
PHOTO_DETAIL_PATH = "路径：{path}"
PHOTO_DETAIL_CAPTURED = "拍摄时间：{time}"
PHOTO_DETAIL_CAPTURED_UNKNOWN = "拍摄时间：未知"
PHOTO_DETAIL_STATUS = "状态：{badge}"
PHOTO_DETAIL_THUMB_PENDING = "缩略图尚未生成；稍后重新打开即可查看。"


# ---- 审核对话框（ReviewDialog） ----
REVIEW_DIALOG_TITLE = "审核待处理识别结果"
REVIEW_APPROVE_SELECTED = "通过所选"
REVIEW_REJECT_SELECTED = "拒绝所选"
REVIEW_APPROVE_ALL = "全部通过"
REVIEW_STATUS_LINE = (
    "待审核 {count} 条。选择记录后点「通过所选」或「拒绝所选」，或点「全部通过」完成整批。"
)
REVIEW_ROW_FORMAT = "照片={photo_label} 人员={person_label} 置信度={confidence:.2f}"
REVIEW_PERSON_UNKNOWN = "未知人员"
STATUS_PHOTO_LIST_EMPTY = "暂无照片——请先扫描照片文件夹"
# G-4：照片墙状态角标（PhotoThumbnailDelegate 右上角小签）。
STATUS_BADGE_PENDING = "待审核"
STATUS_BADGE_APPROVED = "已通过"
STATUS_BADGE_REJECTED = "已拒绝"
STATUS_BADGE_UNMATCHED = "未匹配"
STATUS_BADGE_ARCHIVED = "已归档"
SETTINGS_LANGUAGE_HINT = "（语言切换暂未实装，i18n 为 Out-of-Scope，见 roadmap §13.7）"

# ---- 设置对话框（SettingsDialog） ----
SETTINGS_DIALOG_TITLE = "设置"
SETTINGS_THEME_LABEL = "主题"
SETTINGS_LANGUAGE_LABEL = "语言"
SETTINGS_IMPORT_PATH_LABEL = "默认导入目录"
SETTINGS_EXPORT_PATH_LABEL = "默认导出目录"
SETTINGS_ARCHIVE_ROOT_LABEL = "归档根目录"
SETTINGS_SELECT_ARCHIVE_FOLDER = "选择归档根目录"
SETTINGS_THRESHOLD_LABEL = "匹配阈值"
SETTINGS_MAX_WORKERS_LABEL = "最大工作线程数"
SETTINGS_USE_SYSTEM_DEFAULT = "（使用系统默认）"
SETTINGS_BROWSE_BUTTON = "浏览…"
SETTINGS_SAVE_HINT = "保存后写入平台偏好设置；取消将放弃修改。"
SETTINGS_INVALID_TITLE = "设置无效"
SETTINGS_SELECT_IMPORT_FOLDER = "选择默认导入目录"
SETTINGS_SELECT_EXPORT_FOLDER = "选择默认导出目录"
# 主题/语言选项显示映射（userData 携带契约值；值域镜像
# application.dtos.settings.VALID_THEMES / VALID_LANGUAGES——
# test_ui_translations.py 守护两者同步）。
SETTINGS_THEME_CHOICES = (
    ("跟随系统", "system"),
    ("浅色", "light"),
    ("深色", "dark"),
)
SETTINGS_LANGUAGE_CHOICES = (
    ("跟随系统", "system"),
    ("中文", "zh"),
    ("英语", "en"),
)

# ---- 导出对话框（ExportDialog） ----
EXPORT_DIALOG_TITLE = "导出数据"
EXPORT_SCOPE_GROUP = "导出范围："
EXPORT_SCOPE_ALL = "全部数据（人员、照片、匹配、归档记录）"
EXPORT_SCOPE_CURRENT_BATCH = "当前批次（最近一批处理结果）"
EXPORT_SCOPE_FILTERED = "按当前筛选结果（匹配筛选栏条件的照片）"
EXPORT_SCOPE_ALL_TOOLTIP = "导出完整目录。"
EXPORT_SCOPE_CURRENT_BATCH_TOOLTIP = "当前批次导出暂未实现（FEATURE-004 延后）。"
EXPORT_SCOPE_FILTERED_TOOLTIP = "导出匹配当前筛选条件的照片。需先在筛选栏设置筛选条件。"
EXPORT_NO_ACTIVE_CRITERIA_HINT = "请先在筛选栏设置筛选条件，再启用此范围。"
EXPORT_FORMAT_LABEL = "格式："
EXPORT_FORMAT_XLSX = "Excel (.xlsx)"
EXPORT_FORMAT_CSV = "CSV (.csv)"
EXPORT_FORMAT_HTML = "HTML (.html)"
EXPORT_OUTPUT_LABEL = "输出："
EXPORT_PATH_PLACEHOLDER = "请选择导出文件的保存位置…"
EXPORT_BROWSE_BUTTON = "浏览…"
EXPORT_SAVE_DIALOG_TITLE = "导出另存为"
EXPORT_XLSX_FILTER = "Excel 文件 (*.xlsx)"
EXPORT_CSV_FILTER = "CSV 文件 (*.csv)"
EXPORT_HTML_FILTER = "HTML 文件 (*.html)"
EXPORT_DEFAULT_FILENAME = "export.{extension}"
EXPORT_NO_PATH_TITLE = "未选择输出路径"
EXPORT_NO_PATH_MESSAGE = "请选择导出文件的保存位置。"

# ---- 归档计划预览对话框（ArchivePreviewDialog） ----
ARCHIVE_PREVIEW_TITLE = "归档计划预览"
ARCHIVE_PREVIEW_ROOT = "归档根目录："
ARCHIVE_PREVIEW_PLANNED = "计划条目："
ARCHIVE_PREVIEW_SKIPPED = "跳过："
ARCHIVE_PREVIEW_PERSON_PHOTOS = "{count} 张照片"
ARCHIVE_PREVIEW_CONFLICT_LABEL = "冲突策略："
# 显示标签 → 传给执行器的策略值（skip/overwrite/rename 为 AppSettings/CLI 契约值）。
ARCHIVE_CONFLICT_LABELS = (
    ("跳过（保留现有文件）", "skip"),
    ("覆盖同名文件", "overwrite"),
    ("自动重命名", "rename"),
)
ARCHIVE_DRY_RUN_CHECK = "试运行（仅预览，不写入文件）"

# ---- 重复照片报告对话框（DuplicateReportDialog） ----
DUPLICATE_DIALOG_TITLE = "重复照片报告"
DUPLICATE_HEADER_LABELS = ("成员 / 字段", "值")
DUPLICATE_SUMMARY_NONE = "未发现重复照片——所有内容哈希均唯一。"
DUPLICATE_SUMMARY_FOUND = (
    "发现 {group_count} 组重复照片，涉及 {photo_count} 张。"
    "可点「按建议处置」：每组保留最早注册的一张，其余移除库内登记（磁盘文件不动）。"
)
DUPLICATE_GROUP_NODE = "重复组（哈希 {hash}…）"
DUPLICATE_GROUP_PHOTOS = "{count} 张照片"

# ---- 重复检测控制器（DetectDuplicatesController） ----
DUPLICATE_FAILED_TITLE = "重复照片检测失败"
DUPLICATE_FAILED_MESSAGE = "查重时发生意外错误：\n\n{detail}"

# ---- 控制器拒绝原因（状态栏展示） ----
REFUSAL_SCAN_IN_FLIGHT = "已有扫描任务正在进行。"
REFUSAL_MATCH_IN_FLIGHT = "已有人脸识别任务正在进行。"
REFUSAL_NO_PERSONS = "尚未导入人员，请先通过「导入人员」导入人员名单。"
REFUSAL_NO_PHOTOS = "尚未登记照片，请先通过「扫描文件夹」扫描照片目录。"
REFUSAL_ALL_MATCHED = "已登记的照片均已有识别结果，无需重复运行。"

WORKSPACE_UNKNOWN = "工作区状态尚未加载。"
WORKSPACE_ALL_MATCHED = REFUSAL_ALL_MATCHED + "可前往「审核待处理」查看结果。"
WORKSPACE_MODEL_MISSING = "人脸模型未就绪；请查看模型配置说明，安装模型后重启应用。"
WORKSPACE_MODEL_UNKNOWN = "模型可用性未知；请查看模型配置说明并确认配置后重启应用。"
WORKSPACE_MODEL_HELP = (
    "请在应用配置的 MODEL_PATH 下安装 InsightFace 模型包（默认 buffalo_l），"
    "确认模型目录包含所需 ONNX 文件，然后重启应用。\n"
    "此检查仅表示模型文件已发现，不保证推理运行成功；运行时仍会校验模型。"
)
WORKSPACE_MODEL_HELP_TITLE = "模型配置说明"
WORKSPACE_MATCH_READY = "有 {count} 张照片待识别。"
WORKSPACE_ROOT_UNAVAILABLE = "归档根目录未配置或不可用；请前往「设置」选择可写目录。"
WORKSPACE_ARCHIVE_EMPTY = "暂无可归档照片；请前往「审核待处理」批准识别结果。已归档照片不会重复归档。"
WORKSPACE_ARCHIVE_READY = "有 {count} 张照片可归档；选中照片时仅归档选区。"
WORKSPACE_NEXT_IMPORT = "识别下一步：导入人员"
WORKSPACE_NEXT_SCAN = "识别下一步：扫描文件夹"
WORKSPACE_NEXT_REVIEW = "前往审核待处理"
WORKSPACE_NEXT_SETTINGS = "前往归档设置"
WORKSPACE_NEXT_MODEL = "查看模型配置说明"
REVIEW_EMPTY = "暂无待审核结果。可先扫描照片并运行人脸识别；已完成审核的结果不会在此重复显示。"
WORKSPACE_CANCEL_IDLE = "当前没有可取消的活动任务。"
WORKSPACE_CANCEL_READY = "请求取消当前任务；已完成的结果会保留。"

# ---- 主窗口 · 导航（Batch 3 信息架构） ----
NAV_OVERVIEW = "概览"
NAV_PHOTO_LIBRARY = "照片库"
NAV_REVIEW_CENTER = "审核中心"
NAV_DATA_TOOLS = "数据工具"
NAV_SETTINGS = "设置"
NAV_DATA_TOOLS_HINT = "维护操作：导出数据、检测重复照片、删除人员等低频操作集中于此。"

# ---- 主窗口 · 概览页（流程驱动工作台） ----
OVERVIEW_TITLE = "归档工作台"
OVERVIEW_STEP_IMPORT = "导入人员"
OVERVIEW_STEP_SCAN = "扫描照片"
OVERVIEW_STEP_MATCH = "运行人脸识别"
OVERVIEW_STEP_REVIEW = "人工审核"
OVERVIEW_STEP_ARCHIVE = "安全归档"
OVERVIEW_STEP_DONE_MARK = "✓"
OVERVIEW_STEP_TODO_MARK = "○"
OVERVIEW_STEP_DONE = "已完成"
OVERVIEW_STEP_IMPORT_TODO = "先导入人员名单，识别结果才能归属到人。"
OVERVIEW_STEP_SCAN_TODO = "扫描照片目录，把照片登记进库。"
OVERVIEW_STEP_REVIEW_TODO = "人工确认识别结果；批准后才可归档。"
OVERVIEW_STEP_ARCHIVE_NOTE = "批准的识别结果将按拍摄时间归档到本地归档根目录。"
OVERVIEW_STEP_FORMAT = "{mark} {label}　·　{detail}"
OVERVIEW_PRIVACY_NOTE = (
    "所有照片与识别数据均保存在本机：处理全程离线完成，无需账号，不会自动上传任何文件。"
)
OVERVIEW_PRIMARY_RUN_MATCH = "运行人脸识别"
OVERVIEW_PRIMARY_ARCHIVE = "开始归档"
OVERVIEW_PRIMARY_REVIEW = "前往审核"
OVERVIEW_PRIMARY_IMPORT = "导入人员"
OVERVIEW_PRIMARY_SCAN = "扫描照片"
OVERVIEW_PRIMARY_SETTINGS = "前往归档设置"
OVERVIEW_PRIMARY_MODEL = "查看模型说明"
OVERVIEW_PRIMARY_BUSY = "{label}正在进行，请等待当前任务结束后再开始新操作。"
OVERVIEW_STATUS_NONE = "工作区状态尚未加载。"


# ---- 照片登记删除（Phase E E-4，ADR-034 D1/D3） ----
ACTION_DELETE_PHOTOS = "删除登记"
DELETE_PHOTOS_NO_SELECTION_TITLE = "未选择照片"
DELETE_PHOTOS_NO_SELECTION = (
    "请先在照片列表中选择要移除登记的照片（可按住 Ctrl 或 Shift 多选）。"
)
DELETE_PHOTOS_TITLE = "确认移除照片登记"
DELETE_PHOTOS_CONFIRM = (
    "将从库中移除 {photo_count} 张照片的登记；其 {recognition_count} 条识别结果与 "
    "{archive_count} 条归档记录将一并移除。\n\n仅从库中移除登记，不会删除磁盘上的任何文件。"
)
DELETE_PHOTOS_MISSING_NOTE = "另有 {missing_count} 个所选项目不在库中，将自动跳过。"
DELETE_PHOTOS_CONFIRM_BUTTON = "移除登记"
DELETE_PHOTOS_DONE_TITLE = "删除登记"
DELETE_PHOTOS_DONE = (
    "已移除 {removed} 张照片登记（级联移除识别 {recognition_cascade} 条、归档 {archive_cascade} 条）。"
)

# ---- 人员删除（Phase E E-4，ADR-034 D2/D3） ----
ACTION_DELETE_PERSON = "删除人员"
PERSON_DELETE_DIALOG_TITLE = "删除人员"
PERSON_DELETE_SELECTOR_LABEL = "选择要删除的人员："
PERSON_DELETE_CONFIRM = (
    "将从库中移除人员「{name}」：其 {embedding_count} 条人脸嵌入将一并删除；"
    "{recognition_count} 条识别结果将保留但归属置空（显示为未知人员）。\n\n"
    "该人员的全部照片与磁盘文件均保留，不会删除任何文件。"
)
PERSON_DELETE_BUTTON = "删除该人员"
PERSON_DELETE_EMPTY = "库中暂无人员——请先通过「导入人员」导入人员名单。"
PERSON_DELETE_DONE = (
    "已移除人员「{name}」（删除嵌入 {embedding_cascade} 条、识别归属置空 {recognition_orphaned} 条）。"
)

# ---- 删除失败提示（照片/人员共用） ----
DELETE_FAILED_TITLE = "删除失败"
DELETE_FAILED_MESSAGE = "删除操作时发生意外错误：\n\n{detail}"

# ---- 重复报告处置（Phase E E-4，ADR-034 D6） ----
DUPLICATE_DISPOSE_BUTTON = "按建议处置（每组保留最早一张）"
DUPLICATE_DISPOSE_CONFIRM_TITLE = "确认处置重复照片"
DUPLICATE_DISPOSE_CONFIRM = (
    "共 {group_count} 组重复：每组保留最早注册的一张，其余 {photo_count} 张将从库中移除登记"
    "（级联移除识别 {recognition_count} 条、归档 {archive_count} 条）。\n\n"
    "仅移除库内登记，不删除磁盘文件。"
)
DUPLICATE_DISPOSE_NONE = "当前报告未发现重复组，无需处置。"
DUPLICATE_DISPOSE_DONE = (
    "处置完成：移除 {removed} 张登记（涉及 {groups_affected} 组），拒绝 {rejected} 项。"
)


def task_label(task_name: str) -> str:
    """Map a WorkerTask logic name to its user-visible label (fallback: raw name)."""
    return TASK_LABELS.get(task_name, task_name)
