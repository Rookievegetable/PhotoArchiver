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
STATUS_CANCELLING = "正在取消…"
STATUS_PENDING_REVIEW_COUNT = "{count} 条识别结果待审核"

# ---- 主窗口 · 对话框与流程提示 ----
DIALOG_SELECT_PHOTO_FOLDER = "选择照片文件夹"
DIALOG_SELECT_PEOPLE_FILE = "选择人员文件"
PEOPLE_FILE_FILTER = "人员文件 (*.txt *.csv *.xlsx)"
STATUS_SCANNING_FOLDER = "正在扫描 {folder} …"
STATUS_IMPORTING_FILE = "正在导入 {path} …"
STATUS_ARCHIVING = "正在归档…"
STATUS_EXPORTING = "正在导出…"
STATUS_SCAN_UNAVAILABLE = "扫描不可用。"
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
FILTER_PERSON_LABEL = "人员："
FILTER_ALL_PERSONS = "全部人员"
FILTER_PERSON_TOOLTIP = "按匹配的人员筛选照片。"
FILTER_STATUS_LABEL = "状态："
FILTER_STATUS_ALL = "全部"
FILTER_STATUS_PENDING = "待审核"
FILTER_STATUS_APPROVED = "已通过"
FILTER_STATUS_REJECTED = "已拒绝"
FILTER_FROM_CHECK = "从"
FILTER_TO_CHECK = "至"
FILTER_FROM_TOOLTIP = "筛选捕获时间晚于此时刻（含）的照片。"
FILTER_TO_TOOLTIP = "筛选捕获时间早于此时刻（含）的照片。"
FILTER_CLEAR_BUTTON = "清除"

# ---- 审核对话框（ReviewDialog） ----
REVIEW_DIALOG_TITLE = "审核待处理识别结果"
REVIEW_APPROVE_SELECTED = "通过所选"
REVIEW_REJECT_SELECTED = "拒绝所选"
REVIEW_APPROVE_ALL = "全部通过"
REVIEW_STATUS_LINE = (
    "待审核 {count} 条。选择记录后点「通过所选」或「拒绝所选」，或点「全部通过」完成整批。"
)
REVIEW_ROW_FORMAT = "照片={photo_id} 人员={person_id} 置信度={confidence:.2f}"

# ---- 设置对话框（SettingsDialog） ----
SETTINGS_DIALOG_TITLE = "设置"
SETTINGS_THEME_LABEL = "主题"
SETTINGS_LANGUAGE_LABEL = "语言"
SETTINGS_IMPORT_PATH_LABEL = "默认导入目录"
SETTINGS_EXPORT_PATH_LABEL = "默认导出目录"
SETTINGS_THRESHOLD_LABEL = "匹配阈值"
SETTINGS_MAX_WORKERS_LABEL = "最大工作线程数"
SETTINGS_USE_SYSTEM_DEFAULT = "（使用系统默认）"
SETTINGS_BROWSE_BUTTON = "浏览…"
SETTINGS_SAVE_HINT = "保存后写入平台偏好设置；取消将放弃修改。"
SETTINGS_INVALID_TITLE = "设置无效"
SETTINGS_SELECT_IMPORT_FOLDER = "选择默认导入目录"
SETTINGS_SELECT_EXPORT_FOLDER = "选择默认导出目录"

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
    "本报告为只读；当前版本不支持删除重复照片。"
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


def task_label(task_name: str) -> str:
    """Map a WorkerTask logic name to its user-visible label (fallback: raw name)."""
    return TASK_LABELS.get(task_name, task_name)
