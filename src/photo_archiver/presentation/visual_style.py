"""Centralized visual system for the desktop UI (Batch 7, UI-rules §16).

Single source for the cross-widget look: button hierarchy (primary /
secondary / danger / success / warning / neutral), focus ring, spacing and
the empty-state card, plus the Badge / Card / Banner building blocks
（阶段 1，P0-4）and the main-window chrome（阶段 2：导航 rail NavRail、
objectName="Main" 工具栏、状态栏；只加样式，不动导航映射/工具栏
objectName/CancelTask 契约）. Styles are applied as ONE application-level
stylesheet built here — individual widgets never call ``setStyleSheet``
themselves; they opt into a hierarchy role via :func:`assign_role` (a
dynamic property) or an objectName.

Theme support（阶段 1，P0-1/P0-2/P0-3）: the stylesheet is parameterized by a
theme name (``light`` / ``dark``) resolved from the persisted preference at
startup only（DEC-02=A 重启生效；DEC-03=A 仅启动评估、不监听 OS 运行中变化）.
Every theme-dependent color comes from the token tables below — light values
are the code-frozen现值（P0-1 VERIFIED）；dark values are the P0-1 suggested
values and stay **UNVERIFIED（待 Owner 对照设计板校准）** until Owner sign-off.
Derived tokens added to satisfy the frozen P0-6 contrast standard are marked
inline.

Palette access uses the QSS *function* form — ``palette(Highlight)`` —
because Qt 6 does not support the ``palette.Highlight`` dot syntax: a single
invalid rule makes Qt reject the whole application stylesheet ("Could not
parse application stylesheet"), silently disabling every Batch 7 visual.
Disabled states are expressed with the ``:disabled`` pseudo-state, never as
a second palette() argument. ``test_visual_system.py`` guards both the
syntax and the real rendering (parse-warning capture + pixel probes).

Qt 6.11.1 evidence (render probes, kept here so the card scheme is not
"fixed" back into a broken form): on the plain-QWidget background painting
path every ``palette(<Role>)`` reference collapses to the window color —
only fixed/rgba colors actually paint. The card therefore uses theme-neutral
translucent rgba() tones, which render a visible tint, border and radius in
light AND dark themes; buttons paint through a different path where
``palette(Highlight)`` resolves correctly (probe-verified).
"""

from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractButton,
    QComboBox,
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QWidget,
)

from photo_archiver.application.dtos.settings import DEFAULT_THEME, VALID_THEMES

# Dynamic-property key carrying the visual role on QAbstractButton.
ROLE_PROPERTY = "styleRole"
ROLE_PRIMARY = "primary"
ROLE_DANGER = "danger"
# 阶段 1 角色扩展（§3.2/P0-4 N7：取值域本轮冻结；落点随各阶段任务书）。
ROLE_SUCCESS = "success"
ROLE_WARNING = "warning"
ROLE_NEUTRAL = "neutral"
# 参考图基线（Owner 2026-10-30）：次级着色按钮（编辑/上移/下移/全选等
# 非主操作的浅底描边形态，参考图工具栏次级钮）。
ROLE_SECONDARY = "secondary"
VALID_ROLES = (
    ROLE_PRIMARY, ROLE_DANGER, ROLE_SUCCESS, ROLE_WARNING, ROLE_NEUTRAL,
    ROLE_SECONDARY,
)

# object 属性：可搜索下拉（审核中心身份选择等）——QSS 据此放大展开按钮。
SEARCHABLE_COMBO_PROPERTY = "searchableCombo"
SEARCHABLE_COMBO_MARK = "true"

# objectName hooks for non-button building blocks.
EMPTY_STATE_CARD_OBJECT_NAME = "EmptyStateCard"
# 数据工具页维护操作卡（Owner 2026-10-30 参考图派生：文字按钮行 → 卡片）。
ACTION_CARD_OBJECT_NAME = "ActionCard"
# 详图内嵌导航覆盖控件（任务书阶段 C / D4=B1）：样式走单源 QSS。
NAV_OVERLAY_BUTTON_OBJECT_NAME = "NavOverlayButton"
NAV_POSITION_LABEL_OBJECT_NAME = "NavPositionLabel"
# 主窗口导航 rail 挂点（阶段 2 chrome：QListWidget#NavRail 选择器）。
NAV_RAIL_OBJECT_NAME = "NavRail"
# ── 阶段 1 构建块（P0-4 §1/§2 冻结值）──
BADGE_OBJECT_NAME = "Badge"
CARD_OBJECT_NAME = "Card"
BANNER_OBJECT_NAME = "Banner"
SEVERITY_PROPERTY = "severity"
BADGE_SEVERITIES = ("success", "warning", "danger", "info", "neutral")
BANNER_SEVERITIES = ("info", "warning", "danger")
# ── 五大界面视觉统一（Owner 2026-10-30 参考图基线裁决；派生选择器行）──
# 仅新增 objectName 挂点与 token 选择器行，P0-1 冻结 token 表与既有冻结
# 选择器取值域零改动（P0-4 §3.2 机制）。
PAGE_TITLE_OBJECT_NAME = "PageTitle"
PAGE_SUBTITLE_OBJECT_NAME = "PageSubtitle"
SECTION_TITLE_OBJECT_NAME = "SectionTitle"
STAT_VALUE_OBJECT_NAME = "StatValue"
GLYPH_OBJECT_NAME = "Glyph"
CARD_LIST_OBJECT_NAME = "CardList"

# ── 主题（阶段 1，P0-2 冻结）─────────────────────────────────────────────

THEME_LIGHT = "light"
THEME_DARK = "dark"
VALID_THEME_OUTPUTS = (THEME_LIGHT, THEME_DARK)


class LightDark(Enum):
    """平台亮暗状态枚举（P0-2：测试注入用，纯函数不读真实 OS）。"""

    LIGHT = "light"
    DARK = "dark"


def resolve_theme(preference: object, platform_scheme: LightDark) -> str:
    """Resolve a persisted theme preference into ``light`` / ``dark``（P0-2）.

    纯函数：无 I/O、无 QSettings 访问、不读真实 OS 状态；非法值域唯一来源
    为 ``dtos.settings.VALID_THEMES``（不硬编码第二份）。回退链：缺失/非法
    （含 None、""、大小写变体、其他对象）→ ``DEFAULT_THEME``（"light"）→
    按 ``platform_scheme`` 解析；对非法输入不抛异常，使启动链在偏好缺失/
    损坏时也能完成（DEC-03=A：评估时刻＝应用启动）。
    """
    value = preference if isinstance(preference, str) else None
    if value not in VALID_THEMES:
        value = DEFAULT_THEME
    if value == THEME_LIGHT:
        return THEME_LIGHT
    if value == THEME_DARK:
        return THEME_DARK
    return THEME_LIGHT if platform_scheme is LightDark.LIGHT else THEME_DARK


def detect_platform_scheme(app: QApplication) -> LightDark:
    """Read the OS light/dark state once at startup（DEC-03=A：仅启动评估）.

    ``Unknown``（平台未报告或 offscreen 测试环境）回落 ``LIGHT``。
    不安装任何监听——运行中 OS 亮暗变化不影响主题，下次启动才评估。
    """
    scheme = app.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return LightDark.DARK
    return LightDark.LIGHT


# ── Token 表（P0-1 冻结值；浅色=现值起步 VERIFIED，深色=建议值 UNVERIFIED）──
#
# 所有 token 只在本模块单源 QSS 中消费（DEC-01=A）。深色列与后加的派生
# token 均为 UNVERIFIED（待 Owner 对照设计板校准，U-3 规则）；为满足 P0-6
# 冻结对比度标准而调整/新增的值在行内注明。

LIGHT_TOKENS: dict[str, str] = {
    # 1.1 背景与表面
    "pa-bg-window": "#f0f0f0",  # 参考（QSS 保持 palette(Window)/系统现值，VERIFIED）
    "pa-bg-surface": "#ffffff",  # UNVERIFIED（设计板图面）
    "pa-card-fill-empty": "rgba(127, 127, 127, 0.12)",  # 现值 VERIFIED，跨主题中性
    # 1.2 文本
    "pa-text-primary": "#1a1a1a",  # UNVERIFIED
    # R6/B-3 校准基线：现值 #808080 对窗口底 3.47:1 不达 4.5:1，验收基线=
    # 校准值 #5c5c5c（实算 5.87:1）；深色 UNVERIFIED。
    "pa-text-secondary": "#5c5c5c",
    # 1.3 边框与分隔
    "pa-border": "#e0e0e0",  # UNVERIFIED
    "pa-border-empty": "rgba(127, 127, 127, 0.45)",  # 现值 VERIFIED，跨主题中性
    # 1.5 语义色（C4 danger 浅色=现值不变；C1 三级 span 浅色=现值不变）
    "pa-danger-fg": "#c62828",
    "pa-danger-border": "#8e1f1c",
    "pa-danger-text": "#ffffff",  # 现值（对 #c62828 实算 5.62:1，P0-6 N-4）
    "pa-alert-fg": "#B3261E",  # C1 强冲突（现值）
    "pa-alert-bg": "#F9DEDC",  # C1 强冲突（现值）
    "pa-warning-fg": "#8A5A00",  # C1 弱（现值）
    "pa-warning-bg": "#FBEEC9",  # C1 弱（现值）
    "pa-warning-border": "#8A5A00",  # 派生（=fg），UNVERIFIED
    "pa-warning-text": "#ffffff",  # 派生（按钮字/底 5.93:1），UNVERIFIED
    "pa-info-fg": "#1F4E79",  # C1 信息（现值）
    "pa-info-bg": "#DEEAF6",  # C1 信息（现值）
    "pa-info-border": "#1F4E79",  # 派生（=fg），UNVERIFIED
    # 全新角色（P0-1 §1.5 建议值起步）；success-fg：Owner 裁决 2026-10-29
    # 采用 #107c10（合成淡绿底实测 4.52:1，达 WCAG AA 4.5:1），
    # 原"3.65:1 不达标"深化依据作废；其余 token 维持 UNVERIFIED 待 Owner 校准。
    "pa-success-fg": "#107c10",
    "pa-success-bg": "rgba(16, 124, 16, 0.12)",
    "pa-success-border": "#0b5e0b",
    "pa-success-solid": "#107c10",  # 按钮实底（P0-1 建议值；白字 5.37:1）
    "pa-success-text": "#ffffff",
    "pa-neutral-fg": "#5c5c5c",  # P0-1 建议值；按钮白字 6.69:1
    "pa-neutral-border": "#c8c8c8",  # P0-1 建议值（按钮描边，装饰性）
    "pa-neutral-text": "#ffffff",  # 派生
    # ── Accent（Owner 2026-10-30 参考图基线裁决：应用自带品牌蓝，不再跟随
    # 系统强调色——Owner 机器系统 accent 为紫色，截图实证与参考图差距）。
    # 主蓝 #2563eb 对白字实算 5.17:1 达 WCAG AA；-fg 为浅底上的可读蓝；
    # -soft 为导航选中/着色表面的半透明底。
    "pa-accent": "#2563eb",
    "pa-accent-hover": "#1d4ed8",
    "pa-accent-text": "#ffffff",
    "pa-accent-fg": "#1d4ed8",
    "pa-accent-soft": "rgba(37, 99, 235, 0.10)",
}

DARK_TOKENS: dict[str, str] = {
    # 深色列全部为 P0-1 建议值 UNVERIFIED（待 Owner 对照设计板校准）；
    # 红系色相必须保留（C4 契约：danger 标记不可逆操作）。
    "pa-bg-window": "#202020",
    "pa-bg-surface": "#2b2b2b",
    "pa-card-fill-empty": "rgba(127, 127, 127, 0.12)",  # 跨主题中性（现值起步）
    "pa-text-primary": "#ffffff",
    "pa-text-secondary": "#c8c8c8",
    "pa-border": "#3d3d3d",
    "pa-border-empty": "rgba(127, 127, 127, 0.45)",  # 跨主题中性（现值起步）
    "pa-danger-fg": "#d13438",
    "pa-danger-border": "#e37d7d",
    "pa-danger-text": "#ffffff",  # 对 #d13438 实算 4.93:1 ≥4.5（P0-6）
    "pa-alert-fg": "#F79C97",
    "pa-alert-bg": "rgba(249, 222, 220, 0.10)",
    "pa-warning-fg": "#F2C063",
    "pa-warning-bg": "rgba(251, 238, 201, 0.10)",
    "pa-warning-border": "#F2C063",
    "pa-warning-text": "#3d2e00",  # 派生：浅琥珀底上的深墨（7.87:1）；白字仅 1.6:1
    "pa-info-fg": "#8CBEDF",
    "pa-info-bg": "rgba(222, 234, 246, 0.10)",
    "pa-info-border": "#8CBEDF",
    "pa-success-fg": "#6ccb5f",
    "pa-success-bg": "rgba(108, 203, 95, 0.14)",
    "pa-success-border": "#3fbf3f",
    "pa-success-solid": "#6ccb5f",
    "pa-success-text": "#083b08",  # 派生：亮绿底上的深墨（6.31:1）；白字仅 2.0:1
    "pa-neutral-fg": "#c8c8c8",
    "pa-neutral-border": "#5c5c5c",
    "pa-neutral-text": "#2b2b2b",  # 派生（P0-4 <pa-bg-surface>*）
    # 深色 accent（UNVERIFIED 建议值，同参考图蓝色系提亮）：亮蓝实底配深字
    # （#4f8ef9 对 #0b1220 实算 8.2:1）；-fg 为深底上的可读亮蓝。
    "pa-accent": "#4f8ef9",
    "pa-accent-hover": "#6ba3ff",
    "pa-accent-text": "#0b1220",
    "pa-accent-fg": "#7ab3ff",
    "pa-accent-soft": "rgba(79, 142, 249, 0.16)",
}

_TOKENS: dict[str, dict[str, str]] = {
    THEME_LIGHT: LIGHT_TOKENS,
    THEME_DARK: DARK_TOKENS,
}

_ACTIVE_THEME = THEME_LIGHT
# Captured once so light restores the platform palette verbatim and repeated
# apply calls never stack modifications.
_DEFAULT_PALETTE: QPalette | None = None


def theme_tokens(theme: str) -> dict[str, str]:
    """Return a copy of the token table for ``theme``（测试/校准用）."""
    try:
        return dict(_TOKENS[theme])
    except KeyError as error:
        raise ValueError(f"unknown theme {theme!r}") from error


def active_theme() -> str:
    """Return the theme of the currently installed visual system."""
    return _ACTIVE_THEME


def set_active_theme(theme: str) -> None:
    """Point token resolution at ``theme``（apply_visual_system 内部调用；
    公开供纯 token 级测试在不安装样式表时切换）。"""
    if theme not in _TOKENS:
        raise ValueError(f"unknown theme {theme!r}")
    global _ACTIVE_THEME
    _ACTIVE_THEME = theme


def token(name: str, theme: str | None = None) -> str:
    """Return the value of token ``name`` for ``theme``（缺省＝当前激活主题）.

    C1/C2 迁移（P0-8）的取值入口：富文本 span / QBrush 前景在调用时按当前
    主题解析，不缓存模块级定值。
    """
    table = _TOKENS[theme] if theme is not None else _TOKENS[_ACTIVE_THEME]
    try:
        return table[name]
    except KeyError as error:
        raise KeyError(f"unknown visual token {name!r}") from error


_STYLESHEET_TEMPLATE = """
QPushButton { padding: 4px 14px; }
QPushButton[styleRole="primary"] {
    background-color: ${pa-accent};
    color: ${pa-accent-text};
    border: 1px solid ${pa-accent};
    font-weight: 600;
    padding: 5px 18px;
}
QPushButton[styleRole="primary"]:hover {
    background-color: ${pa-accent-hover};
    border: 1px solid ${pa-accent-hover};
}
QPushButton[styleRole="secondary"], QToolButton[styleRole="secondary"] {
    background-color: ${pa-card-fill-empty};
    color: ${pa-text-primary};
    border: 1px solid ${pa-border};
    font-weight: 400;
    padding: 5px 14px;
}
QPushButton[styleRole="secondary"]:hover, QToolButton[styleRole="secondary"]:hover {
    border: 1px solid ${pa-accent};
}
QPushButton[styleRole="danger"] {
    background-color: ${pa-danger-fg};
    color: ${pa-danger-text};
    border: 1px solid ${pa-danger-border};
    font-weight: 600;
    padding: 5px 18px;
}
QPushButton[styleRole="success"] {
    background-color: ${pa-success-solid};
    color: ${pa-success-text};
    border: 1px solid ${pa-success-border};
    font-weight: 600;
    padding: 5px 18px;
}
QPushButton[styleRole="warning"] {
    background-color: ${pa-warning-fg};
    color: ${pa-warning-text};
    border: 1px solid ${pa-warning-border};
    font-weight: 600;
    padding: 5px 18px;
}
QPushButton[styleRole="neutral"] {
    background-color: ${pa-neutral-fg};
    color: ${pa-neutral-text};
    border: 1px solid ${pa-neutral-border};
    font-weight: 400;
    padding: 5px 18px;
}
QPushButton[styleRole="primary"]:disabled {
    color: palette(ButtonText);
    background-color: palette(Button);
    border: 1px solid palette(Mid);
    font-weight: 400;
}
QPushButton[styleRole="danger"]:disabled {
    color: palette(ButtonText);
    background-color: palette(Button);
    border: 1px solid palette(Mid);
    font-weight: 400;
}
QPushButton[styleRole="success"]:disabled,
QPushButton[styleRole="warning"]:disabled,
QPushButton[styleRole="neutral"]:disabled {
    color: palette(ButtonText);
    background-color: palette(Button);
    border: 1px solid palette(Mid);
    font-weight: 400;
}
QPushButton:focus, QToolButton:focus {
    border: 2px solid palette(Highlight);
}
QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus {
    border: 2px solid palette(Highlight);
}
QListWidget:focus, QListView:focus {
    border: 1px solid palette(Highlight);
}
QComboBox[searchableCombo="true"]::drop-down {
    width: 24px;
}
QComboBox[searchableCombo="true"]::down-arrow {
    width: 16px;
    height: 16px;
}
QWidget#EmptyStateCard {
    background-color: rgba(127, 127, 127, 0.12);
    border: 1px solid rgba(127, 127, 127, 0.45);
    border-radius: 6px;
}
QPushButton#NavOverlayButton {
    background-color: rgba(0, 0, 0, 120);
    color: #ffffff;
    border: none;
    border-radius: 6px;
    font-size: 20px;
    padding: 0px;
}
QPushButton#NavOverlayButton:hover {
    background-color: rgba(0, 0, 0, 190);
}
QLabel#NavPositionLabel {
    background-color: rgba(0, 0, 0, 140);
    color: #ffffff;
    border-radius: 4px;
    padding: 2px 8px;
}
QLabel#Badge {
    padding: 2px 8px;
    border-radius: 4px;
}
QLabel#Badge[severity="success"] {
    color: ${pa-success-fg};
    background-color: ${pa-success-bg};
    border: 1px solid ${pa-success-border};
}
QLabel#Badge[severity="warning"] {
    color: ${pa-warning-fg};
    background-color: ${pa-warning-bg};
    border: 1px solid ${pa-warning-border};
}
QLabel#Badge[severity="danger"] {
    color: ${pa-alert-fg};
    background-color: ${pa-alert-bg};
    border: 1px solid ${pa-danger-border};
}
QLabel#Badge[severity="info"] {
    color: ${pa-info-fg};
    background-color: ${pa-info-bg};
    border: 1px solid ${pa-info-border};
}
QLabel#Badge[severity="neutral"] {
    color: ${pa-text-secondary};
    background-color: ${pa-card-fill-empty};
    border: 1px solid ${pa-border};
}
QFrame#Card {
    background-color: ${pa-bg-surface};
    border: 1px solid ${pa-border};
    border-radius: 6px;
}
QFrame#Banner {
    border-radius: 6px;
    padding: 8px 12px;
}
QFrame#Banner[severity="info"] {
    color: ${pa-info-fg};
    background-color: ${pa-info-bg};
    border: 1px solid ${pa-info-border};
}
QFrame#Banner[severity="warning"] {
    color: ${pa-warning-fg};
    background-color: ${pa-warning-bg};
    border: 1px solid ${pa-warning-border};
}
QFrame#Banner[severity="danger"] {
    color: ${pa-alert-fg};
    background-color: ${pa-alert-bg};
    border: 1px solid ${pa-danger-border};
}
QFrame#Banner[severity="info"] QLabel {
    color: ${pa-info-fg};
}
QFrame#Banner[severity="warning"] QLabel {
    color: ${pa-warning-fg};
}
QFrame#Banner[severity="danger"] QLabel {
    color: ${pa-alert-fg};
}
QToolBar#Main {
    background-color: ${pa-bg-surface};
    border-bottom: 1px solid ${pa-border};
    padding: 4px 8px;
    spacing: 6px;
}
QToolBar#Main::separator {
    background-color: ${pa-border};
    width: 1px;
    margin: 6px 4px;
}
QListWidget#NavRail {
    background-color: ${pa-bg-surface};
    border: none;
    border-right: 1px solid ${pa-border};
}
QListWidget#NavRail:focus {
    border: 1px solid palette(Highlight);
}
QListWidget#NavRail::item {
    padding: 8px 12px;
    margin: 2px 8px;
    border-radius: 6px;
}
QListWidget#NavRail::item:hover {
    background-color: rgba(127, 127, 127, 0.18);
}
QListWidget#NavRail::item:selected {
    background-color: ${pa-accent-soft};
    color: ${pa-accent-fg};
    border-left: 3px solid ${pa-accent};
}
QListView#PhotoWall {
    background-color: ${pa-bg-window};
    border: none;
}
QPushButton#ActionCard {
    background-color: ${pa-bg-surface};
    color: ${pa-text-primary};
    border: 1px solid ${pa-border};
    border-radius: 8px;
    padding: 12px 14px;
    text-align: left;
    font-size: 13px;
}
QPushButton#ActionCard:hover {
    border: 1px solid ${pa-accent};
}
QPushButton#ActionCard:disabled {
    color: palette(ButtonText);
    background-color: palette(Button);
    border: 1px solid palette(Mid);
}
QStatusBar {
    background-color: ${pa-bg-surface};
    border-top: 1px solid ${pa-border};
}
QStatusBar QProgressBar {
    border: 1px solid ${pa-border};
    border-radius: 3px;
    background-color: ${pa-card-fill-empty};
    text-align: center;
}
QStatusBar QProgressBar::chunk {
    background-color: palette(Highlight);
}
/* 批量终审进度条（Owner 2026-10-31）：聚类结果对话框内、执行期显示。 */
QProgressBar#BatchProgress {
    background-color: ${pa-card-fill-empty};
    border: 1px solid ${pa-border};
    border-radius: 4px;
    text-align: center;
    color: ${pa-text-primary};
    min-height: 16px;
    max-height: 18px;
}
QProgressBar#BatchProgress::chunk {
    background-color: ${pa-accent};
    border-radius: 3px;
}
QLabel#PageTitle {
    font-size: 20px;
    font-weight: 600;
    color: ${pa-text-primary};
    background: transparent;
    border: none;
}
QLabel#PageSubtitle {
    font-size: 12px;
    color: ${pa-text-secondary};
    background: transparent;
    border: none;
}
QLabel#SectionTitle {
    font-size: 14px;
    font-weight: 600;
    color: ${pa-text-primary};
    background: transparent;
    border: none;
}
QLabel#StatValue {
    font-size: 18px;
    font-weight: 600;
    color: ${pa-text-primary};
    background: transparent;
    border: none;
}
QLabel#Glyph {
    font-family: "Segoe Fluent Icons", "Segoe MDL2 Assets";
    font-size: 14px;
    color: ${pa-text-secondary};
    background: transparent;
    border: none;
}
QTableWidget {
    background-color: ${pa-bg-surface};
    alternate-background-color: rgba(127, 127, 127, 0.06);
    gridline-color: ${pa-border};
    border: 1px solid ${pa-border};
    border-radius: 6px;
    selection-background-color: palette(Highlight);
    selection-color: palette(HighlightedText);
}
QTableWidget::item {
    padding: 4px 8px;
    border: none;
}
/* ::item 一旦有样式规则，选中态的绘制就整体走 QSS——必须显式给出
   :selected 背景/文字，否则选中行＝无背景＋selection-color 白字 → 白底
   白字整行「空白」（Owner 实机 2026-10-31 实证）。 */
QTableWidget::item:selected {
    background-color: palette(Highlight);
    color: palette(HighlightedText);
}
QHeaderView::section {
    background-color: ${pa-bg-surface};
    color: ${pa-text-secondary};
    border: none;
    border-bottom: 1px solid ${pa-border};
    padding: 6px 8px;
    font-weight: 600;
}
QTableCornerButton::section {
    background-color: ${pa-bg-surface};
    border: none;
}
QListWidget#CardList {
    background: transparent;
    border: none;
}
QListWidget#CardList::item {
    background-color: ${pa-bg-surface};
    border: 1px solid ${pa-border};
    border-radius: 6px;
    margin: 4px 2px;
    padding: 8px;
    color: ${pa-text-primary};
    /* Owner 2026-10-31：选中项内缘黑框＝原生焦点矩形（State_HasFocus）
       叠加在选中描边内——显式关掉 outline（导航 rail 同类问题同解）。 */
    outline: none;
}
QListWidget#CardList::item:selected {
    border: 1px solid palette(Highlight);
    color: ${pa-text-primary};
    outline: none;
}
QComboBox, QDateTimeEdit {
    background-color: ${pa-bg-surface};
    border: 1px solid ${pa-border};
    border-radius: 4px;
    padding: 3px 8px;
}
"""


def build_stylesheet(theme: str = THEME_LIGHT) -> str:
    """Return the application-level stylesheet for ``theme``（唯一替换点）."""
    if theme not in _TOKENS:
        raise ValueError(f"unknown theme {theme!r}")
    qss = _STYLESHEET_TEMPLATE
    for name, value in _TOKENS[theme].items():
        qss = qss.replace("${" + name + "}", value)
    if "${" in qss:
        leftover = qss[qss.index("${"):qss.index("${") + 40]
        raise AssertionError(f"unresolved QSS token placeholder near {leftover!r}")
    return qss


def apply_visual_system(app: QApplication, theme: str = THEME_LIGHT) -> None:
    """Install the visual system once, right after QApplication creation.

    ``theme`` 由启动链经 ``resolve_theme`` 解析（P0-2/P0-3）；两个主题都按
    token 建立应用级 QPalette（§6.3 覆盖范围：应用级 QSS＋QApplication
    palette）并统一盖上 accent 角色（Highlight/HighlightedText/Link＝品牌
    蓝，Owner 2026-10-30 参考图基线）。浅色不再恢复平台默认 palette——
    深色系统上那是深色调色板，会与浅色 QSS 混合渲染（截图实证）。
    """
    global _ACTIVE_THEME, _DEFAULT_PALETTE
    if theme not in _TOKENS:
        raise ValueError(f"unknown theme {theme!r}")
    if _DEFAULT_PALETTE is None:
        _DEFAULT_PALETTE = QPalette(app.palette())
    app.setStyleSheet(build_stylesheet(theme))
    if theme == THEME_DARK:
        app.setPalette(_accent_palette(_dark_palette(_DEFAULT_PALETTE), DARK_TOKENS))
    else:
        app.setPalette(_accent_palette(_light_palette(_DEFAULT_PALETTE), LIGHT_TOKENS))
    _ACTIVE_THEME = theme


def _accent_palette(palette: QPalette, table: dict[str, str]) -> QPalette:
    """Stamp the brand accent onto the palette roles the QSS/delegates read.

    ``palette(Highlight)``（QSS）与委托的活调色板（选中描边/勾选章）都从
    这两个角色取色——参考图基线（Owner 2026-10-30）下它们必须解析为应用
    自带品牌蓝，而不是系统强调色。
    """
    palette.setColor(QPalette.ColorRole.Highlight, QColor(table["pa-accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(table["pa-accent-text"]))
    palette.setColor(QPalette.ColorRole.Link, QColor(table["pa-accent-fg"]))
    return palette


def _light_palette(base: QPalette) -> QPalette:
    """Build the deterministic light palette from LIGHT_TOKENS（参考图基线）.

    Owner 2026-10-30 裁决推翻「浅色恢复平台默认 palette」：深色系统上平台
    默认调色板是深色（截图实证＝浅色 QSS 与深色调色板混合渲染，界面发暗）。
    浅色主题自此按参考图显式建立——任何 OS 亮暗下渲染一致。
    """
    t = LIGHT_TOKENS
    palette = QPalette(base)

    def c(name: str) -> QColor:
        return QColor(t[name])

    palette.setColor(QPalette.ColorRole.Window, c("pa-bg-window"))
    palette.setColor(QPalette.ColorRole.WindowText, c("pa-text-primary"))
    palette.setColor(QPalette.ColorRole.Base, c("pa-bg-surface"))
    palette.setColor(QPalette.ColorRole.AlternateBase, c("pa-bg-window"))
    palette.setColor(QPalette.ColorRole.Text, c("pa-text-primary"))
    palette.setColor(QPalette.ColorRole.Button, c("pa-bg-surface"))
    palette.setColor(QPalette.ColorRole.ButtonText, c("pa-text-primary"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, c("pa-bg-surface"))
    palette.setColor(QPalette.ColorRole.ToolTipText, c("pa-text-primary"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, c("pa-text-secondary"))
    palette.setColor(QPalette.ColorRole.Mid, c("pa-border"))
    palette.setColor(QPalette.ColorRole.Light, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Dark, QColor("#d9d9d9"))
    disabled = QPalette.ColorGroup.Disabled
    palette.setColor(disabled, QPalette.ColorRole.WindowText, c("pa-text-secondary"))
    palette.setColor(disabled, QPalette.ColorRole.Text, c("pa-text-secondary"))
    palette.setColor(disabled, QPalette.ColorRole.ButtonText, c("pa-text-secondary"))
    return palette


def _dark_palette(base: QPalette) -> QPalette:
    """Build the dark application palette from P0-1 dark tokens（UNVERIFIED）.

    Highlight / HighlightedText / Link 保留系统角色（P0-1 pa-accent VERIFIED
    ＝palette 角色，palette() 函数形式红线 §10-12）。
    """
    palette = QPalette(base)
    t = DARK_TOKENS

    def c(name: str) -> QColor:
        return QColor(t[name])

    palette.setColor(QPalette.ColorRole.Window, c("pa-bg-window"))
    palette.setColor(QPalette.ColorRole.WindowText, c("pa-text-primary"))
    palette.setColor(QPalette.ColorRole.Base, c("pa-bg-surface"))
    palette.setColor(QPalette.ColorRole.AlternateBase, c("pa-bg-window"))
    palette.setColor(QPalette.ColorRole.Text, c("pa-text-primary"))
    palette.setColor(QPalette.ColorRole.Button, c("pa-bg-surface"))
    palette.setColor(QPalette.ColorRole.ButtonText, c("pa-text-primary"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, c("pa-bg-surface"))
    palette.setColor(QPalette.ColorRole.ToolTipText, c("pa-text-primary"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, c("pa-text-secondary"))
    palette.setColor(QPalette.ColorRole.Mid, c("pa-border"))
    # UNVERIFIED（派生明暗梯度，Owner 校准项）
    palette.setColor(QPalette.ColorRole.Light, QColor("#4a4a4a"))
    palette.setColor(QPalette.ColorRole.Dark, QColor("#141414"))
    disabled = QPalette.ColorGroup.Disabled
    palette.setColor(disabled, QPalette.ColorRole.WindowText, c("pa-text-secondary"))
    palette.setColor(disabled, QPalette.ColorRole.Text, c("pa-text-secondary"))
    palette.setColor(disabled, QPalette.ColorRole.ButtonText, c("pa-text-secondary"))
    return palette


def repolish(widget: QWidget) -> None:
    """Public restyle helper: force QSS re-evaluation（§3.2 规则 2）.

    每次 ``setProperty()`` 之后必须调用；Badge/Card/Banner 构建块的
    ``set_*_severity`` helper 内部已调用，动态改属性的其他调用方复用本函数。
    """
    _repolish(widget)


def assign_role(button: QAbstractButton, role: str) -> None:
    """Tag a button with a visual role and refresh any installed stylesheet."""
    button.setProperty(ROLE_PROPERTY, role)
    _repolish(button)


def _repolish(widget: QWidget) -> None:
    """Force the QSS engine to re-evaluate property-dependent selectors."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


def style_badge(label: QLabel, severity: str) -> None:
    """Tag a QLabel as a Badge building block（P0-4：objectName＋severity）。"""
    set_badge_severity(label, severity)


def set_badge_severity(label: QLabel, severity: str) -> None:
    """Set (or change) a Badge's severity and repolish（取值域外＝无样式）。"""
    if severity not in BADGE_SEVERITIES:
        raise ValueError(
            f"badge severity {severity!r} not in {BADGE_SEVERITIES}"
        )
    label.setObjectName(BADGE_OBJECT_NAME)
    label.setProperty(SEVERITY_PROPERTY, severity)
    _repolish(label)


def style_card(frame: QFrame) -> None:
    """Tag a QFrame as a Card building block（WA_StyledBackground 必需）。"""
    frame.setObjectName(CARD_OBJECT_NAME)
    frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    _repolish(frame)


def style_banner(frame: QFrame, severity: str) -> None:
    """Tag a QFrame as a Banner building block（P0-4：info/warning/danger）。"""
    set_banner_severity(frame, severity)


def set_banner_severity(frame: QFrame, severity: str) -> None:
    """Set (or change) a Banner's severity and repolish（取值域外＝无样式）。"""
    if severity not in BANNER_SEVERITIES:
        raise ValueError(
            f"banner severity {severity!r} not in {BANNER_SEVERITIES}"
        )
    frame.setObjectName(BANNER_OBJECT_NAME)
    frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    frame.setProperty(SEVERITY_PROPERTY, severity)
    _repolish(frame)


def style_nav_overlay_button(button: QPushButton) -> None:
    """Give a detail-dialog overlay navigation button the shared look."""
    button.setObjectName(NAV_OVERLAY_BUTTON_OBJECT_NAME)
    _repolish(button)


def style_nav_position_label(label) -> None:
    """Give the detail-dialog navigation position counter the shared look."""
    label.setObjectName(NAV_POSITION_LABEL_OBJECT_NAME)
    _repolish(label)


def style_empty_state_card(page: QWidget) -> None:
    """Give an empty-state page the shared card look via its objectName.

    ``WA_StyledBackground`` makes the stylesheet background/border/radius
    actually paint for this widget — required for any QWidget that Qt does
    not style through a plain fill (and harmless for plain instances).
    """
    page.setObjectName(EMPTY_STATE_CARD_OBJECT_NAME)
    page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


def button_role(button: QPushButton) -> str | None:
    """Return the assigned role (test/QA hook)."""
    return button.property(ROLE_PROPERTY)


def mark_searchable_combo(combo: QComboBox) -> None:
    """Tag a combo as searchable — the stylesheet enlarges its drop-down.

    2026-10-01 审核中心：身份下拉接智能搜索的同时放大展开按钮。除 QSS
    属性选择器（各平台默认 drop-down 宽度不一）外，另按平台指标
    (PM_IndicatorWidth) 比例设置最小宽度——保证"明显更大"在所有平台成立，
    而不依赖平台默认基线。combo 整体宽度交给布局，不在此写死。
    """
    combo.setProperty(SEARCHABLE_COMBO_PROPERTY, SEARCHABLE_COMBO_MARK)
    indicator = combo.style().pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth)
    combo.setMinimumWidth(indicator * 4)
    _repolish(combo)


# ── Fluent 图标（Owner 2026-10-30 裁决：DEC-10=A 按参考图推翻，按图实施）──
# 零新增运行时依赖（DEC-13=A）：仅使用 Windows 系统自带图标字体
# （Segoe Fluent Icons / Segoe MDL2 Assets）离线渲染位图；两字体均缺失时
# 优雅降级（调用方保留文字，仅无图标），绝不崩溃。码位经 offscreen 渲染
# 探针逐一目检（round-1 dev 取证）。
ICON_FONT_FAMILIES = ("Segoe Fluent Icons", "Segoe MDL2 Assets")

ICONS: dict[str, str] = {
    "home": "",          # 概览
    "photo": "",         # 照片库
    "people": "",        # 人员与分组
    "review": "",        # 审核中心（对勾）
    "data": "",          # 数据工具
    "settings": "",      # 设置
    "search": "",        # 搜索
    "add": "",           # 添加
    "add_friend": "",    # 添加人员（AddFriend＝人形+加号，语义贴合「新增人员」）
    "edit": "",          # 编辑
    "up": "",            # 上移
    "down": "",          # 下移
    "delete": "",        # 删除
    "more": "",          # 更多 …
    "chevron_down": "",  # 下箭头
    "chevron_right": "", # 右箭头
    "calendar": "",      # 日历/拍摄时间
    "play": "",          # 运行
    "sync": "",          # 重新解析/刷新
    "download": "",      # 确认导入
    "view": "",          # 查看结果（眼睛）
    "check": "",         # 对勾
    "info": "",          # 信息
    "warning": "",       # 警告
    "history": "",       # 历史记录
    "chart": "",         # 统计
    "person": "",        # 单人
    "filter": "",        # 筛选
    "document": "",      # 文档/名单文件
    "save": "",          # 保存/归档
}


def _icon_font_family() -> str | None:
    """Return the first available system icon font, or ``None``（优雅降级）."""
    from PySide6.QtGui import QFontDatabase

    families = set(QFontDatabase.families())
    for family in ICON_FONT_FAMILIES:
        if family in families:
            return family
    return None


def icon_font_available() -> bool:
    """Return True when a system icon font is present (test/QA hook)."""
    return _icon_font_family() is not None


def fluent_pixmap(
    name: str,
    color: str | None = None,
    size_px: int = 16,
) -> QPixmap:
    """Render one Fluent glyph as a monochrome QPixmap（fluent_icon 的位图层）.

    ``name`` 是 :data:`ICONS` 的键；``color`` 为色值字符串（缺省＝次要文本
    token 当前主题值）。位图按 2× 渲染并设 devicePixelRatio(2)，高分屏不
    发虚。字体缺失时返回空 QPixmap（调用方仅无图标，绝不崩溃）。
    """
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFont, QPainter, QPixmap

    glyph = ICONS.get(name)
    if glyph is None:
        raise KeyError(f"unknown icon glyph {name!r}")
    family = _icon_font_family()
    if family is None:
        return QPixmap()
    ratio = 2.0
    physical = max(4, int(size_px * ratio))
    pixmap = QPixmap(physical, physical)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    font = QFont(family)
    font.setPixelSize(physical)
    painter.setFont(font)
    painter.setPen(QColor(color) if color is not None else QColor(token("pa-text-secondary")))
    painter.drawText(
        QRectF(0, 0, physical, physical),
        Qt.AlignmentFlag.AlignCenter, glyph,
    )
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def fluent_icon(
    name: str,
    color: str | None = None,
    size_px: int = 14,
) -> QIcon:
    """Render one Fluent glyph as a monochrome QIcon（零依赖图标方案）.

    字体缺失时返回空 QIcon（按钮/标签仅显示文字）。
    """
    return QIcon(fluent_pixmap(name, color, size_px))


def style_page_title(label) -> None:
    """Tag a QLabel as a page title（QLabel#PageTitle 选择器）."""
    label.setObjectName(PAGE_TITLE_OBJECT_NAME)
    _repolish(label)


def style_page_subtitle(label) -> None:
    """Tag a QLabel as a page subtitle（QLabel#PageSubtitle 选择器）."""
    label.setObjectName(PAGE_SUBTITLE_OBJECT_NAME)
    _repolish(label)


def style_section_title(label) -> None:
    """Tag a QLabel as a section title（QLabel#SectionTitle 选择器）."""
    label.setObjectName(SECTION_TITLE_OBJECT_NAME)
    _repolish(label)


def style_stat_value(label) -> None:
    """Tag a QLabel as a big statistics value（QLabel#StatValue 选择器）."""
    label.setObjectName(STAT_VALUE_OBJECT_NAME)
    _repolish(label)


def style_glyph_label(label) -> None:
    """Tag a QLabel as a Fluent glyph carrier（QLabel#Glyph 字体族）."""
    label.setObjectName(GLYPH_OBJECT_NAME)
    _repolish(label)


def style_card_list(list_widget) -> None:
    """Tag a QListWidget as a card list（QListWidget#CardList 卡片化列表）."""
    list_widget.setObjectName(CARD_LIST_OBJECT_NAME)
    _repolish(list_widget)


def assign_button_icon(button, name: str, color: str | None = None) -> None:
    """Give a QPushButton/QToolButton a Fluent glyph icon（缺失即无图标）."""
    button.setIcon(fluent_icon(name, color))


def assign_label_icon(label, name: str, color: str | None = None, size_px: int = 18) -> None:
    """Give a QLabel a Fluent glyph pixmap（页头图标等装饰位；缺失即空白）."""
    label.setPixmap(fluent_pixmap(name, color, size_px))
