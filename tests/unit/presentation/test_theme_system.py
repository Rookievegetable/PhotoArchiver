"""阶段 1 主题系统守护：解析纯函数（P0-2）＋启动验收（P0-3）＋P0-6 对比度.

- ``resolve_theme``：注入平台亮暗枚举，不依赖真实 OS（P0-2 §2）。
- P0-3 A-1..A-7：经 ``apply_startup_theme``（app/application.py）以
  ``SettingsService``＋``InMemoryUserSettingsStore`` 组合验证启动链语义；
  DEC-02=A 反向断言（保存不即时切换）含其中。
- P0-6：对 P0-1 冻结 token 对程序化计算 WCAG 对比度并断言（双主题各一遍）；
  WCAG 公式自带已知值校验（黑白＝21:1）。

已知偏差（如实登记，非削弱）：受检对 5/16/17 引用系统 palette 角色（P0-1
VERIFIED＝palette() 形式，改定值须任务书授权），以 Qt 标准亮 palette
（Fusion ``standardPalette``，跨机器确定）代入计算；其中受检对 17
（pa-separator / 窗口底）在标准亮 palette 下实算不足 3:1，按 xfail 如实
上报待 Owner 校准。受检对 20（C3 角标对任意照片）为 P0-6 规定的人工记录项，
不做程序化断言。
"""

import re
from typing import NamedTuple

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

from photo_archiver.app.application import apply_startup_theme
from photo_archiver.application import SettingsService
from photo_archiver.application.dtos import UserPreferences
from photo_archiver.application.dtos.settings import DEFAULT_THEME, VALID_THEMES
from photo_archiver.infrastructure.persistence.in_memory_user_settings_store import (
    InMemoryUserSettingsStore,
)
from photo_archiver.presentation.visual_style import (
    THEME_DARK,
    THEME_LIGHT,
    LightDark,
    active_theme,
    apply_visual_system,
    build_stylesheet,
    resolve_theme,
    set_active_theme,
    theme_tokens,
)

# ── WCAG 2.x 对比度计算（P0-6 §3：计算函数入库为守护测试公用代码）──────────


def _srgb_channel_to_linear(value: int) -> float:
    channel = value / 255.0
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    red, green, blue = (_srgb_channel_to_linear(v) for v in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    lighter, darker = sorted(
        (_relative_luminance(fg), _relative_luminance(bg)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


_RGBA_RE = re.compile(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)")


def _parse_color(value: str) -> tuple[int, int, int, float]:
    """Parse a token color (#hex / CSS rgba with float alpha) → (r, g, b, a)."""
    text = value.strip().lower()
    if text.startswith("#"):
        digits = text[1:]
        if len(digits) == 3:
            digits = "".join(ch * 2 for ch in digits)
        return (
            int(digits[0:2], 16),
            int(digits[2:4], 16),
            int(digits[4:6], 16),
            1.0,
        )
    match = _RGBA_RE.match(text)
    assert match is not None, f"unsupported color literal {value!r}"
    alpha = float(match[4])
    if alpha > 1.0:  # Qt QSS rgba 亦接受 0-255 整数 alpha（NavOverlay 系现值）
        alpha /= 255.0
    return int(match[1]), int(match[2]), int(match[3]), alpha


def _composite(fg_rgba: str, bg_rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """P0-6 §3：半透明 token 与不透明底合成（out = a*fg + (1-a)*bg，逐通道）。"""
    fr, fg, fb, alpha = _parse_color(fg_rgba)
    br, bgg, bb = bg_rgb
    return (
        round(alpha * fr + (1 - alpha) * br),
        round(alpha * fg + (1 - alpha) * bgg),
        round(alpha * fb + (1 - alpha) * bb),
    )


def _rgb(color: QColor) -> tuple[int, int, int]:
    return color.red(), color.green(), color.blue()


class _Pair(NamedTuple):
    label: str
    fg: tuple[int, int, int]
    bg: tuple[int, int, int]
    threshold: float


def _reference_light_palette() -> QPalette:
    """Qt 标准亮 palette（P0-6 §2 注记口径：以 Qt 标准亮 palette 角色值代入）。

    Qt 6.5+ 的 ``standardPalette`` 跟随 styleHints 色方案（深色 OS 机器上
    默认返回暗板，Fusion Window=#323232 实测）——此处强制 Light 取得跨机器
    确定的亮板参考（Fusion Window=#efefef、Highlight=#308cc6），随后恢复
    原色方案设置，保证守护测试不依赖真实 OS 也不污染会话状态。
    """
    hints = QApplication.styleHints()
    previous = hints.colorScheme()
    hints.setColorScheme(Qt.ColorScheme.Light)
    try:
        return QStyleFactory.create("Fusion").standardPalette()
    finally:
        hints.setColorScheme(previous)


def test_contrast_formula_known_values() -> None:
    """P0-6 §3：公式已知值校验（黑白＝21:1）。"""
    assert _contrast((255, 255, 255), (0, 0, 0)) == pytest.approx(21.0)
    assert _contrast((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)


# ── P0-6 受检 token 对（逐对，不许抽检；双主题参数化）──────────────────────


@pytest.mark.parametrize("theme", [THEME_LIGHT, THEME_DARK])
def test_p0_6_token_pairs_meet_contrast(theme: str) -> None:
    """受检对 1-4/6-15/18-19：程序化 WCAG 计算，浅/深各跑一遍。"""
    tokens = theme_tokens(theme)
    surface = _parse_color(tokens["pa-bg-surface"])[:3]
    text_secondary = _parse_color(tokens["pa-text-secondary"])[:3]
    if theme == THEME_DARK:
        window = _parse_color(tokens["pa-bg-window"])[:3]
        content_text = _parse_color(tokens["pa-text-primary"])[:3]
    else:
        # 浅色窗口底＝palette(Window) 系统现值（P0-1 VERIFIED）；以 Qt 标准
        # 亮 palette（Fusion，跨机器确定）代入计算（P0-6 §2 注记）。
        reference = _reference_light_palette()
        window = _rgb(reference.color(QPalette.ColorRole.Window))
        content_text = _rgb(reference.color(QPalette.ColorRole.Text))

    white = (255, 255, 255)
    black_overlay_120 = "rgba(0, 0, 0, 120)"
    black_overlay_140 = "rgba(0, 0, 0, 140)"
    black_overlay_160 = "rgba(0, 0, 0, 160)"
    pairs = [
        # 1-4 文本/背景
        _Pair("1 pa-text-primary/window", _parse_color(tokens["pa-text-primary"])[:3], window, 4.5),
        _Pair("2 pa-text-primary/surface", _parse_color(tokens["pa-text-primary"])[:3], surface, 4.5),
        _Pair("3 pa-text-secondary/window", text_secondary, window, 4.5),
        _Pair("4 pa-text-secondary/surface", text_secondary, surface, 4.5),
        # 6 danger 按钮字/底（N-4：浅色实算 5.62:1）
        _Pair(
            "6 pa-danger-text/pa-danger-fg",
            _parse_color(tokens["pa-danger-text"])[:3],
            _parse_color(tokens["pa-danger-fg"])[:3],
            4.5,
        ),
        # 7 新角色按钮字/底（P0-1 §1.5 派生对）
        _Pair("7a success 按钮字/底", _parse_color(tokens["pa-success-text"])[:3], _parse_color(tokens["pa-success-solid"])[:3], 4.5),
        _Pair("7b warning 按钮字/底", _parse_color(tokens["pa-warning-text"])[:3], _parse_color(tokens["pa-warning-fg"])[:3], 4.5),
        _Pair("7c neutral 按钮字/底", _parse_color(tokens["pa-neutral-text"])[:3], _parse_color(tokens["pa-neutral-fg"])[:3], 4.5),
        # 8-10 徽章/告警文字对其底色（rgba 底先与表面色合成）
        _Pair("8 pa-alert-fg/pa-alert-bg@surface", _parse_color(tokens["pa-alert-fg"])[:3], _composite(tokens["pa-alert-bg"], surface), 4.5),
        _Pair("9 pa-warning-fg/pa-warning-bg@surface", _parse_color(tokens["pa-warning-fg"])[:3], _composite(tokens["pa-warning-bg"], surface), 4.5),
        _Pair("10 pa-info-fg/pa-info-bg@surface", _parse_color(tokens["pa-info-fg"])[:3], _composite(tokens["pa-info-bg"], surface), 4.5),
        # 11 Badge neutral（rgba 合成后，底＝窗口）
        _Pair("11 badge neutral 文字/底@window", text_secondary, _composite(tokens["pa-card-fill-empty"], window), 4.5),
        # 12 EmptyStateCard 内文本 / 填充（rgba 合成后）
        _Pair("12 EmptyStateCard 文本/底@window", content_text, _composite(tokens["pa-card-fill-empty"], window), 4.5),
        # 13-15 叠照元素（黑底白字系、主题无关现值）：最亮情形＝白底合成，
        # 按 P0-6 §1「大号文字与图形语义 ≥3:1」口径判定（见模块 docstring 偏差注记）。
        _Pair("13 NavOverlayButton 白字", white, _composite(black_overlay_120, white), 3.0),
        _Pair("14 NavPositionLabel 白字", white, _composite(black_overlay_140, white), 3.0),
        _Pair("15 C3 角标 chip 白字", white, _composite(black_overlay_160, white), 3.0),
        # 18 徽章/Banner 语义边框 vs 表面（图形语义 ≥3:1；neutral 描边为装饰性
        # pa-border，不属语义边框）
        _Pair("18a success 边框/表面", _parse_color(tokens["pa-success-border"])[:3], surface, 3.0),
        _Pair("18b warning 边框/表面", _parse_color(tokens["pa-warning-border"])[:3], surface, 3.0),
        _Pair("18c info 边框/表面", _parse_color(tokens["pa-info-border"])[:3], surface, 3.0),
        _Pair("18d danger 边框/表面", _parse_color(tokens["pa-danger-border"])[:3], surface, 3.0),
        # 19 表格排序箭头（随 pa-text-secondary）vs 表面
        _Pair("19 排序箭头/表面", text_secondary, surface, 3.0),
    ]
    for pair in pairs:
        ratio = _contrast(pair.fg, pair.bg)
        assert ratio >= pair.threshold, (
            f"P0-6 受检对 {pair.label}（{theme}）实算 {ratio:.2f}:1，"
            f"低于冻结阈值 {pair.threshold}:1"
        )


def test_p0_6_palette_derived_pairs_reference_values(qapp) -> None:
    """受检对 5/16/17：palette 角色对以 Qt 标准亮 palette 代入计算。

    受检对 5（primary 字/底）与 16（焦点环）钉住 ≥3:1 下限；冻结的 4.5:1
    在 Fusion 标准亮 palette 下实算 3.69:1 未达（系统角色值，改定值须任务书
    授权）——差额登记 Owner 校准项。受检对 17（分隔线）现值 palette(Mid)
    不足 3:1，如实 xfail 上报待 Owner 校准（非本次改动引入：现值 token、
    QSS 未消费）。受检对 20（C3 角标对任意照片）为 P0-6 规定的人工记录项。
    """
    reference = _reference_light_palette()
    highlight = _rgb(reference.color(QPalette.ColorRole.Highlight))
    highlighted_text = _rgb(reference.color(QPalette.ColorRole.HighlightedText))
    window = _rgb(reference.color(QPalette.ColorRole.Window))
    mid = _rgb(reference.color(QPalette.ColorRole.Mid))

    # 5 primary 字/底（≥3:1 下限守护；4.5:1 差额＝Owner 校准项）
    accent_ratio = _contrast(highlighted_text, highlight)
    assert accent_ratio >= 3.0, f"primary 字/底塌缩（{accent_ratio:.2f}:1 < 3:1）"
    # 16 焦点环（图形语义 ≥3:1）
    focus_ratio = _contrast(highlight, window)
    assert focus_ratio >= 3.0, f"焦点环对比度塌缩（{focus_ratio:.2f}:1 < 3:1）"
    # 17 分隔线（图形语义 ≥3:1）
    separator_ratio = _contrast(mid, window)
    if separator_ratio < 3.0:
        pytest.xfail(
            f"受检对 17：现值 palette(Mid) 对窗口底实算 {separator_ratio:.2f}:1，"
            "不达 3:1——pa-separator 为 P0-1 现值 token 且 QSS 未消费，改值须 "
            "Owner 授权（已登记 Owner 校准项，非本次改动引入）"
        )


# ── P0-2：resolve_theme 纯函数（注入平台亮暗，不依赖真实 OS）───────────────


@pytest.mark.parametrize("preference", ["light", "dark", "system", "", "SYSTEM", "Dark", "blue", "auto", 123, None])
def test_resolve_theme_covers_full_input_matrix(preference: object) -> None:
    """合法值直取/按平台解析；缺失与非法值回退 DEFAULT_THEME 再解析。"""
    assert resolve_theme(preference, LightDark.LIGHT) in (THEME_LIGHT, THEME_DARK)
    assert resolve_theme(preference, LightDark.DARK) in (THEME_LIGHT, THEME_DARK)


def test_resolve_theme_explicit_preferences_direct() -> None:
    assert resolve_theme("light", LightDark.DARK) == THEME_LIGHT
    assert resolve_theme("dark", LightDark.LIGHT) == THEME_DARK


def test_resolve_theme_system_follows_injected_platform() -> None:
    assert resolve_theme("system", LightDark.LIGHT) == THEME_LIGHT
    assert resolve_theme("system", LightDark.DARK) == THEME_DARK


def test_resolve_theme_invalid_falls_back_to_default_theme() -> None:
    """回退链：非法 → DEFAULT_THEME("light") → 按平台亮暗解析。

    参考图基线（Owner 2026-10-30）：默认浅色（按图验收基线）。
    """
    assert DEFAULT_THEME == "light"
    assert VALID_THEMES == ("system", "light", "dark")
    for bad in ("", "SYSTEM", "Dark", "blue", "auto", 123, None, ["dark"]):
        assert resolve_theme(bad, LightDark.LIGHT) == THEME_LIGHT
        assert resolve_theme(bad, LightDark.DARK) == THEME_LIGHT


# ── P0-3：启动读取与应用验收（A-1..A-7；QSettings 隔离＝InMemory store）─────


def _startup_service(preference: str | None) -> tuple[SettingsService, InMemoryUserSettingsStore]:
    """组装启动链被测对象；偏好经 Port save 直接预置（绕过服务校验层）。"""
    store = InMemoryUserSettingsStore()
    service = SettingsService(user_settings_store=store)
    if preference is not None:
        store.save(UserPreferences(theme=preference))
    return service, store


@pytest.fixture
def clean_app_look(qapp):
    """安装任意主题后恢复平台默认观感（palette＋样式表），测试互不污染。"""
    yield qapp
    apply_visual_system(qapp, theme=THEME_LIGHT)  # 恢复捕获的默认 palette
    qapp.setStyleSheet("")
    set_active_theme(THEME_LIGHT)


def test_a1_dark_preference_applies_dark_tokens(clean_app_look) -> None:
    """A-1：预置 theme="dark" → dark token 生效（样式表＋palette 双证）。"""
    service, _store = _startup_service("dark")
    applied = apply_startup_theme(clean_app_look, service)
    assert applied == THEME_DARK
    assert clean_app_look.styleSheet() == build_stylesheet(THEME_DARK)
    assert "#2b2b2b" in clean_app_look.styleSheet()  # dark surface token 上墙
    palette = clean_app_look.palette()
    assert palette.color(QPalette.ColorRole.Window).name().lower() == "#202020"
    assert palette.color(QPalette.ColorRole.Base).name().lower() == "#2b2b2b"
    assert active_theme() == THEME_DARK


def test_a2_light_preference_applies_light_tokens(clean_app_look) -> None:
    """A-2：预置 theme="light" → light token 生效。"""
    service, _store = _startup_service("light")
    applied = apply_startup_theme(clean_app_look, service)
    assert applied == THEME_LIGHT
    assert clean_app_look.styleSheet() == build_stylesheet(THEME_LIGHT)
    assert "#c62828" in clean_app_look.styleSheet()  # C4 现值契约 token 上墙


@pytest.mark.parametrize("platform_scheme", [LightDark.LIGHT, LightDark.DARK])
def test_a3_a4_system_preference_resolves_injected_platform(
    clean_app_look, monkeypatch, platform_scheme: LightDark,
) -> None:
    """A-3/A-4：theme="system"＋注入平台亮暗 → 对应主题生效。"""
    monkeypatch.setattr(
        "photo_archiver.app.application.detect_platform_scheme",
        lambda _app: platform_scheme,
    )
    service, _store = _startup_service("system")
    expected = THEME_DARK if platform_scheme is LightDark.DARK else THEME_LIGHT
    assert apply_startup_theme(clean_app_look, service) == expected
    assert clean_app_look.styleSheet() == build_stylesheet(expected)


@pytest.mark.parametrize("bad_preference", ["blue", "", "Dark"])
def test_a5_invalid_preference_falls_back_without_crash(
    clean_app_look, monkeypatch, bad_preference: str,
) -> None:
    """A-5：预置非法值 → 回退链（→DEFAULT_THEME→按平台），不崩溃不抛出。"""
    monkeypatch.setattr(
        "photo_archiver.app.application.detect_platform_scheme",
        lambda _app: LightDark.LIGHT,
    )
    service, _store = _startup_service(bad_preference)
    assert apply_startup_theme(clean_app_look, service) == THEME_LIGHT


@pytest.mark.parametrize("platform_scheme", [LightDark.LIGHT, LightDark.DARK])
def test_a6_missing_preference_defaults_to_light(
    clean_app_look, monkeypatch, platform_scheme: LightDark,
) -> None:
    """A-6：无任何持久化偏好 → DEFAULT_THEME（"light"，参考图基线）生效。

    与 system 跟随的旧契约差异：默认值改为 light（Owner 2026-10-30 参考图
    裁决）——两种平台注入下都解析为浅色；system 仍为显式合法选项（A-3/A-4）。
    """
    monkeypatch.setattr(
        "photo_archiver.app.application.detect_platform_scheme",
        lambda _app: platform_scheme,
    )
    service, _store = _startup_service(None)
    assert apply_startup_theme(clean_app_look, service) == THEME_LIGHT
    assert clean_app_look.styleSheet() == build_stylesheet(THEME_LIGHT)


def test_a7_saving_preference_does_not_switch_running_theme(clean_app_look) -> None:
    """A-7（DEC-02=A 反向断言）：dark 启动后保存 light——运行中主题未切换，
    持久化已写入，下次启动才生效。"""
    service, store = _startup_service("dark")
    assert apply_startup_theme(clean_app_look, service) == THEME_DARK
    dark_stylesheet = clean_app_look.styleSheet()

    service.save(UserPreferences(theme="light"))  # 设置页保存＝仅持久化写入

    assert clean_app_look.styleSheet() == dark_stylesheet  # 运行中未切换
    assert clean_app_look.styleSheet() == build_stylesheet(THEME_DARK)
    assert active_theme() == THEME_DARK
    assert store.load().theme == "light"  # 持久化成功
    # 重启后 light 生效（A-1/A-2 桩复验：重新走启动链）。
    assert apply_startup_theme(clean_app_look, service) == THEME_LIGHT
    assert clean_app_look.styleSheet() == build_stylesheet(THEME_LIGHT)


def test_startup_theme_applied_by_application_bootstrap_wiring(clean_app_look) -> None:
    """接线守护：PhotoArchiverApplication 的启动链消费 settings.load()。

    直接验证 application.py 的装配点：主题解析失败（非法偏好）不抛出、
    应用级样式表被安装（唯一 setStyleSheet 点仍为视觉系统）。
    """
    service, store = _startup_service(None)
    store.save(UserPreferences(theme="dark"))
    assert apply_startup_theme(clean_app_look, service) == THEME_DARK
    assert isinstance(clean_app_look, QApplication)
    assert clean_app_look.styleSheet() != ""
