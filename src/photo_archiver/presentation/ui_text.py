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
    "import_confirm": "导入确认",
    "scan_and_register_photos": "扫描",
    "match_persons": "人脸识别",
    "run_recognition": "人脸识别",
    "face_clustering": "人脸聚类",
    "archive_photos": "归档",
    "export": "导出",
}
STATUS_READY = "就绪"
STATUS_TASK_STARTED = "{label}已开始"
STATUS_TASK_COMPLETED = "{label}完成"

# ---- 导入预览与确认（人员导入重设计 阶段 A） ----
IMPORT_PREVIEW_TITLE = "导入预览与确认"
IMPORT_PREVIEW_FILE_LABEL = "文件："
IMPORT_PREVIEW_ENCODING_LABEL = "编码："
IMPORT_PREVIEW_DELIMITER_LABEL = "分隔符："
IMPORT_PREVIEW_SHEET_LABEL = "工作表："
IMPORT_PREVIEW_HEADER_LABEL = "首行为表头"
IMPORT_PREVIEW_REPARSE_BUTTON = "重新解析"
IMPORT_PREVIEW_COL_RAW = "原始内容"
IMPORT_PREVIEW_COL_NAME = "姓名"
IMPORT_PREVIEW_COL_IDENTITY = "工号"
IMPORT_PREVIEW_COL_DEPARTMENT = "部门"
IMPORT_PREVIEW_COL_NOTE = "备注"
IMPORT_PREVIEW_COL_WARNINGS = "告警"
IMPORT_PREVIEW_COL_ACTION = "处理动作"
IMPORT_PREVIEW_ACTION_CREATE = "新建人员"
IMPORT_PREVIEW_ACTION_MERGE = "合并到已有人员"
IMPORT_PREVIEW_ACTION_SKIP = "跳过"
IMPORT_PREVIEW_SPLIT_BUTTON = "拆分"
IMPORT_PREVIEW_COUNTS = "将新建 {create} · 合并 {merge} · 跳过 {skip} · 告警 {warnings}"
IMPORT_PREVIEW_CONFIRM_BUTTON = "确认导入"
IMPORT_PREVIEW_CANCEL_BUTTON = "取消"
IMPORT_PREVIEW_EMPTY_FILE = "文件中没有可导入的数据行。"
IMPORT_PREVIEW_CONFIRM_LARGE = "名单超过 {limit} 行，确认将在后台执行，完成后状态栏显示结果。"
# 告警 code → 中文模板（与解析服务的结构化告警一一对应）
IMPORT_WARNING_TEXTS = {
    "empty_name": "姓名为空，默认跳过",
    "multi_name": "该单元格疑似包含 {detail} 个姓名，可点击「拆分」",
    "group_title": "疑似组标题（{detail}），默认跳过，不作为人员写入",
    "identity_duplicate_in_file": "工号在名单内重复（强冲突）：{detail}，默认跳过",
    "identity_duplicate_db": "工号与库内已有人员重复（强冲突），将合并名单顺序",
    "name_department_duplicate_in_file": "姓名+部门在名单内重复（弱冲突）",
    "name_department_duplicate_db": "姓名+部门与库内已有人员重复（弱冲突），将合并名单顺序",
}
IMPORT_PREVIEW_DEFAULT_WARNING = "{code}: {detail}"  # 未知告警兜底
STATUS_IMPORT_DRAFT_PARSED = "已解析 {rows} 行草稿，请在预览中确认。"
STATUS_IMPORT_CONFIRMED = "导入完成：新建 {imported} · 合并 {merged} · 跳过 {skipped}"
STATUS_IMPORT_CONFIRM_ERRORS = "；{count} 行失败（详情见日志）"
STATUS_IMPORT_CONFIRM_WORKER = "导入确认已提交后台执行，完成后显示结果。"
# ---- 人员与分组页（人员导入重设计 阶段 B） ----
PEOPLE_PAGE_HINT = (
    "名单顺序即「照片库」人员筛选下拉的展示顺序：拖动行或使用「上移 / 下移」调整，改动立即保存。"
    "「来源批次」可回看某次导入带入的人员（回看态为只读）。"
)
PEOPLE_PAGE_ADD_BUTTON = "新增人员"
PEOPLE_PAGE_EDIT_BUTTON = "编辑"
PEOPLE_PAGE_DELETE_BUTTON = "删除所选"
PEOPLE_PAGE_MOVE_UP = "上移"
PEOPLE_PAGE_MOVE_DOWN = "下移"
PEOPLE_PAGE_BATCH_FILTER_LABEL = "来源批次："
PEOPLE_PAGE_BATCH_ALL = "全部批次"
PEOPLE_PAGE_BATCH_ENTRY = "{file_name}（{person_count} 人）"
PEOPLE_PAGE_BATCH_FILTER_HINT = "回看态为只读：调整顺序请先切回「全部批次」。"
PEOPLE_PAGE_COL_ORDER = "顺序"
PEOPLE_PAGE_COL_NAME = "姓名"
PEOPLE_PAGE_COL_IDENTITY = "工号"
PEOPLE_PAGE_COL_DEPARTMENT = "部门"
PEOPLE_PAGE_COL_NOTE = "备注"
PEOPLE_PAGE_COL_BATCH = "来源批次"
PEOPLE_PAGE_COL_ACTIONS = "操作"
PEOPLE_PAGE_MANUAL_SOURCE = "手工新增"
PEOPLE_PAGE_EMPTY = "名单为空。可用「新增人员」手工录入，或用工具栏「导入人员」批量导入名单。"
PEOPLE_PAGE_EMPTY_FILTERED = "该批次没有仍在名单中的人员（人员可能在后续导入中被合并或删除）。"
PEOPLE_PAGE_DIALOG_ADD_TITLE = "新增人员"
PEOPLE_PAGE_DIALOG_EDIT_TITLE = "编辑人员"
PEOPLE_PAGE_NAME_LABEL = "姓名（必填）"
PEOPLE_PAGE_IDENTITY_LABEL = "工号 / 证件号"
PEOPLE_PAGE_DEPARTMENT_LABEL = "部门"
PEOPLE_PAGE_NOTE_LABEL = "备注"
PEOPLE_PAGE_SAVE_BUTTON = "保存"
PEOPLE_PAGE_CANCEL_BUTTON = "取消"
PEOPLE_PAGE_ADDED = "已新增「{name}」，排在名单末尾。"
PEOPLE_PAGE_EDITED = "已保存「{name}」的修改。"
PEOPLE_PAGE_REORDERED = "名单顺序已保存（{count} 人）。"
PEOPLE_PAGE_DELETED = "已删除「{name}」：照片全部保留、历史识别归属转为未分配。"
PEOPLE_PAGE_SAVE_FAILED = "保存失败：{detail}"
PEOPLE_PAGE_SAVE_FAILED_TITLE = "无法保存名单修改"
PEOPLE_PAGE_DELETE_FAILED = "删除失败：{detail}"
PEOPLE_PAGE_DELETE_FAILED_TITLE = "无法删除人员"
# AUDIT 2026-09-20：识别完成必须区分"无脸"与"读图失败"，不得静默吞掉不可读照片。
STATUS_MATCH_SUMMARY = "处理 {processed} 张 · 检出人脸 {faces} 张"
STATUS_MATCH_UNREADABLE = "无法读取 {unreadable} 张（文件缺失或路径不可用）"
# 阶段 C Commit 3：新识别运行（RecognitionRun）完成摘要——五类计数一次给全，
# 与 run 统计列同口径（face/unreadable/no_face/error/in_scope/out_of_scope）。
STATUS_RUN_SUMMARY = (
    "检出人脸 {faces} 张 · 无法读取 {unreadable} 张 · 无脸 {no_face} 张 · 检测异常 {errors} 张"
)
STATUS_RUN_SCOPE_SUMMARY = "范围内 {in_scope} 张 · 范围外 {out_of_scope} 张"
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
PEOPLE_FILE_FILTER = "人员文件 (*.csv *.tsv *.txt *.xlsx *.xlsm *.xls)"
STATUS_SCANNING_FOLDER = "正在扫描 {folder} …"
STATUS_IMPORTING_FILE = "正在导入 {path} …"
STATUS_ARCHIVING = "正在归档…"
STATUS_EXPORTING = "正在导出…"
STATUS_SCAN_UNAVAILABLE = "扫描不可用。"
STATUS_SCAN_ENUMERATION_FAILED = "扫描目录枚举失败：{detail}"
STATUS_MATCH_UNAVAILABLE = "人脸识别不可用。"

# 归档前置警告
ARCHIVE_DIALOG_TITLE = "归档"
ARCHIVE_ROOT_SETUP_PROMPT = (
    "尚未配置归档根目录，无法归档。\n\n是否现在打开「设置」配置归档根目录？"
)
ARCHIVE_ROOT_SETUP_BUTTON = "去设置"
ARCHIVE_ROOT_SETUP_CANCEL = "暂不"
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

# ---- 照片库 · 选择操作簇（2026-09-30 选中态优化） ----
# 「全选」常驻可见（0 选区时也能建立第一次选区）；「清除选择」仅在有选区时出现。
SELECT_ALL_PHOTOS = "全选"
CLEAR_SELECTION = "清除选择"

# ---- 照片详情对话框（Batch 4） ----
PHOTO_DETAIL_TITLE = "照片详情"
PHOTO_DETAIL_NAME = "文件名：{name}"
PHOTO_DETAIL_PATH = "路径：{path}"
PHOTO_DETAIL_CAPTURED = "拍摄时间：{time}"
PHOTO_DETAIL_CAPTURED_UNKNOWN = "拍摄时间：未知"
PHOTO_DETAIL_STATUS = "状态：{badge}"
PHOTO_DETAIL_THUMB_PENDING = "缩略图尚未生成；稍后重新打开即可查看。"

# ---- 照片详情 · 高清预览（2026-09-30） ----
# 用户点击【查看大图】后才异步受控解码原图；失败保留缩略图并轻提示。
PHOTO_DETAIL_VIEW_FULL = "查看大图"
PHOTO_DETAIL_HD_LOADING = "正在加载高清预览..."
PHOTO_DETAIL_HD_FAILED = "高清预览加载失败，已保留缩略图"


# ---- 审核中心页面（2026-10-01 页面化，原 ReviewDialog） ----
REVIEW_DIALOG_TITLE = "审核待处理识别结果"
# 引导条：两条身份建立路径的分工——冷启动配对链（ordered_suggestion → 人工确认）
# 在「人员与分组」页；本页只做 D-1 个别处理。只引导，不自动化身份归属。
REVIEW_GUIDANCE_TEXT = (
    "冷启动身份建立：识别 → 运行人脸聚类 → 人物配对工作台（按名单顺序生成配对建议）"
    "→ 人工确认后身份生效并沉淀样本。本页用于零散结果的个别处理：选择人员后「通过」"
    "写入归属（人工身份为最终结果）。"
)
REVIEW_GUIDANCE_PAIRING_BUTTON = "前往人物配对工作台"
REVIEW_APPROVE_SELECTED = "通过所选"
REVIEW_REJECT_SELECTED = "拒绝所选"
REVIEW_APPROVE_ALL = "全部通过"
REVIEW_APPROVE_SELECTED_COUNTED = "通过所选（{count}）"
REVIEW_REJECT_SELECTED_COUNTED = "拒绝所选（{count}）"
REVIEW_APPROVE_ALL_COUNTED = "全部通过（{count}）"
REVIEW_APPROVE_ALL_CONFIRM_TITLE = "确认全部通过"
REVIEW_APPROVE_ALL_CONFIRM = (
    "将把全部 {count} 条待审核结果标记为「已通过」，完成后它们会从待审核列表移除。\n"
    "界面内没有批量撤销操作；已通过的照片仍可在照片墙中筛选复核。\n\n确定继续？"
)
REVIEW_STATUS_LINE = (
    "待审核 {count} 条。选择记录后点「通过所选」或「拒绝所选」，或点「全部通过」完成整批。"
)
REVIEW_ROW_FORMAT = "照片={photo_label}　人员={person_label}"
REVIEW_ROW_DETAIL_FORMAT = "{confidence_text} · 状态：{status}"
REVIEW_CONFIDENCE_FORMAT = "置信度：{band}（{value:.2f}）"
# Stage 4 D-1：人工批准时必须能指定身份，否则批准后的行无法进入归档。
REVIEW_IDENTITY_LABEL = "批准时指定人员"
REVIEW_IDENTITY_UNRESOLVED = "（未指定）"
REVIEW_IDENTITY_HINT = (
    "新识别结果不含身份归属；在此选择人员后「通过」才会写入归属并可进入归档。"
)
REVIEW_NO_IDENTITY_WARNING = (
    "未选择人员：通过后该结果不会进入归档计划（归档只消费带人员归属的已通过记录）。"
)
# 无相似度证据（Stage 4 BLK-5）：confidence 落库为 NULL，不是 0.0。
REVIEW_CONFIDENCE_NO_EVIDENCE = "无相似度证据"
REVIEW_CONFIDENCE_VERY_HIGH = "很高"
REVIEW_CONFIDENCE_HIGH = "较高"
REVIEW_CONFIDENCE_MEDIUM = "中等"
REVIEW_CONFIDENCE_LOW = "较低"
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
EXPORT_SCOPE_FILTERED = "按当前筛选结果（匹配筛选栏条件的照片）"
EXPORT_SCOPE_ALL_TOOLTIP = "导出完整目录。"
EXPORT_SCOPE_FILTERED_TOOLTIP = "导出匹配当前筛选条件的照片。需先在筛选栏设置筛选条件。"
EXPORT_NO_ACTIVE_CRITERIA_HINT = "请先在筛选栏设置筛选条件，再启用此范围。"
EXPORT_FILTERED_SUMMARY = "当前筛选：{summary}；预计导出 {count} 张照片。"
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
ARCHIVE_CONFLICT_HINTS = {
    "skip": "跳过：保留目标位置现有同名文件，冲突条目本次不写入（最安全）。",
    "overwrite": "覆盖：用本次归档文件替换目标位置的同名文件，原文件内容会丢失。",
    "rename": "自动重命名：同名时保存为 x.dup-1.jpg 等新文件名，两个文件都保留。",
}
ARCHIVE_DRY_RUN_CHECK = "试运行（仅预览，不写入文件）"
ARCHIVE_EXECUTE_BUTTON = "开始归档"
ARCHIVE_DRY_RUN_BUTTON = "执行试运行"
ARCHIVE_SCOPE_LABEL = "范围："
ARCHIVE_SCOPE_SELECTED = "已选 {count} 张照片（仅归档选中项）"
ARCHIVE_SCOPE_ALL = "全部已通过照片（已归档过的不会重复归档）"
ARCHIVE_SAMPLE_HEADER = "源 → 目标示例："
ARCHIVE_SAMPLE_ROW = "{source} → {target}"
ARCHIVE_SAMPLE_TRUNCATED = "（仅显示前 {shown} 项，共 {total} 项）"

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
# 阶段 C Commit 3：重跑是一等公民——已全部识别的照片不再拒绝识别入口。
WORKSPACE_REANALYSIS_READY = (
    "所有照片均已有识别结果；再次运行将创建新的识别运行（可重新分析）。"
)

# ---- 人脸聚类入口与结果（D-4） ----
REFUSAL_CLUSTER_IN_FLIGHT = "已有人脸聚类任务正在进行。"
CLUSTER_UNAVAILABLE = "人脸聚类不可用。"
CLUSTER_PAGE_GROUP = "人脸聚类"
CLUSTER_PAGE_RUN_LABEL = "识别运行"
CLUSTER_PAGE_RUN_BUTTON = "运行人脸聚类"
CLUSTER_PAGE_RESULTS_BUTTON = "查看聚类结果"
CLUSTER_PAGE_HINT = (
    "对选定识别运行的人脸观测执行聚类；聚类只读已有检测数据，不重新识别，"
    "也不会产生人员归属（人员配对属后续阶段）。重新运行会生成新的聚类代际，"
    "历史结果保留。"
)
CLUSTER_PAGE_RUN_ENTRY = "{created_at} · {status} · {faces} 张脸"
CLUSTER_PAGE_NO_RUNS = "尚无识别运行；请先运行人脸识别。"
CLUSTER_RESULTS_TITLE = "人脸聚类结果"
CLUSTER_RESULTS_GENERATION_LABEL = "聚类代际"
CLUSTER_RESULTS_GENERATION_ENTRY = "{created_at} · {status} · {clusters} 簇 / {members} 张脸"
CLUSTER_RESULTS_EMPTY = "该识别运行尚无聚类结果；请先运行人脸聚类。"
CLUSTER_RESULTS_EMPTY_CLUSTERS = "该代聚类没有产生任何簇（范围内无人脸观测）。"
CLUSTER_RESULTS_CLUSTER_ENTRY = "第 {ordinal} 组 · {count} 张脸 · 首拍 {time}"
CLUSTER_RESULTS_NO_CAPTURED = "时间缺失"
CLUSTER_RESULTS_MEMBER_ENTRY = "{photo} · 脸 {index} · 检测 {det:.2f} · 证据 {conf:.2f}"

# ---- 人物配对工作台（Stage E） ----
PAIRING_WORKBENCH_TITLE = "人物配对工作台"
PAIRING_WORKBENCH_ENTRY_BUTTON = "人物配对工作台"
PAIRING_WORKBENCH_HINT = (
    "为聚类组指派人员：建议仅作参考（建议状态=待确认），人工确认后才写入"
    "正式归属并沉淀人脸样本；拒绝/改派不影响原始聚类数据。"
)
PAIRING_WORKBENCH_GENERATION_LABEL = "聚类代际"
PAIRING_WORKBENCH_GENERATION_ENTRY = "{created_at} · {status} · {clusters} 簇"
PAIRING_WORKBENCH_GENERATE_BUTTON = "生成建议"
PAIRING_WORKBENCH_CLUSTER_ENTRY = "第 {ordinal} 组 · {count} 张脸 · {assignment}"
PAIRING_WORKBENCH_ASSIGNMENT_LABEL = {
    "suggested": "待确认（{source} · {score}）",
    "confirmed": "已确认：{person}",
    "rejected": "已拒绝：{person}",
    "unassigned": "未指派",
}
PAIRING_WORKBENCH_SOURCE_LABELS = {
    "ordered_suggestion": "顺序建议",
    "sample_match": "样本匹配",
    "manual": "人工指派",
}
PAIRING_WORKBENCH_MEMBER_LABEL = "人员"
PAIRING_WORKBENCH_CONFIRM_BUTTON = "确认建议"
PAIRING_WORKBENCH_REJECT_BUTTON = "拒绝建议"
PAIRING_WORKBENCH_ASSIGN_BUTTON = "指派该人员"
PAIRING_WORKBENCH_UNASSIGN_BUTTON = "解除映射"
PAIRING_WORKBENCH_UNKNOWN_BUTTON = "标记陌生人"
PAIRING_WORKBENCH_IGNORE_BUTTON = "忽略组"
PAIRING_WORKBENCH_NO_CLUSTERS = "该代没有可指派的簇。"
PAIRING_WORKBENCH_NO_ASSIGNMENT_HINT = "尚未生成建议；可点击「生成建议」或直接指派人员。"
PAIRING_WORKBENCH_NO_ROSTER = "人员名单为空；请先导入人员。"
PAIRING_WORKBENCH_SUGGESTED_DONE = (
    "已生成 {suggestions} 条建议（样本匹配 {sample_matched} · 顺序配对 {ordered}）"
)
PAIRING_WORKBENCH_CONFIRMED = "已确认归属：{person}"
PAIRING_WORKBENCH_REJECTED = "已拒绝该建议"
PAIRING_WORKBENCH_ASSIGNED = "已人工指派：{person}"
PAIRING_WORKBENCH_UNASSIGNED = "已解除映射"
PAIRING_WORKBENCH_STATE_SET = "已标记为 {state}"
PAIRING_WORKBENCH_OP_FAILED_TITLE = "配对操作失败"

CLUSTER_RUN_STATUS_LABELS = {
    "created": "已创建",
    "running": "运行中",
    "completed": "已完成",
    "failed": "已失败",
    "cancelled": "已取消",
}
STATUS_CLUSTER_SUMMARY = "{clusters} 簇 · {members} 张脸 · 排除 {excluded} 张观测"


def cluster_run_status_label(status: str) -> str:
    """Map a FaceClusterRun status to its user-visible label (fallback: raw)."""
    return CLUSTER_RUN_STATUS_LABELS.get(status, status)


# ---- 识别范围选择对话框（阶段 C Commit 3） ----
RECOGNITION_SCOPE_DIALOG_TITLE = "识别范围选择"
RECOGNITION_SCOPE_OK_BUTTON = "确定"
RECOGNITION_SCOPE_PHOTO_GROUP = "照片选择范围"
RECOGNITION_SCOPE_RANGE_GROUP = "人脸数量范围"
RECOGNITION_SCOPE_ALL_PHOTOS = "全部照片"
RECOGNITION_SCOPE_SELECTED_PHOTOS = "仅选中照片（{count} 张）"
RECOGNITION_SCOPE_RETRY_PHOTOS = "仅重试上次失败的照片（{count} 张）"
RECOGNITION_SCOPE_EXPORT_FAILURES = "导出上次失败清单"
RECOGNITION_SCOPE_NO_FAILURES = "上次识别运行没有可重试的失败照片。"
RECOGNITION_FAILURE_EXPORT_TITLE = "导出失败清单"
RECOGNITION_FAILURE_EXPORT_DONE = "已导出 {count} 条失败记录到：{path}"
RECOGNITION_SCOPE_RANGE_HINT = (
    "只对检出人脸数落在选中范围的照片给出识别归属；范围外照片仍会保存全部人脸检测记录。"
)
RECOGNITION_SCOPE_AT_LEAST_ONE = "请至少选择一个人脸数量范围。"
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
NAV_PEOPLE = "人员与分组"
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
DELETE_PHOTOS_IRREVERSIBLE = "该操作会从数据库移除登记，界面内没有撤销操作。"
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
