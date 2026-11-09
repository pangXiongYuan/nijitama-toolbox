# -*- coding: utf-8 -*-
"""
app.py —— にじたま 工具箱（PySide6 深色卡片式界面）

左侧导航：启动游戏 / 刷本 / 设置 / 日志
详细功能说明见同目录的「功能说明.txt」
"""
import os
import shutil
import socket
import subprocess
import sys
import time

import _bootstrap  # noqa: F401

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPixmap, QTextCursor)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFrame, QHBoxLayout,
    QLabel, QMainWindow, QPlainTextEdit, QProgressBar,
    QPushButton, QSpinBox, QStackedWidget, QTabWidget, QTextBrowser,
    QVBoxLayout, QWidget,
)

import config
import paths
from version import APP_NAME, VERSION

HERE = paths.HERE
ASSETS = paths.ASSETS_DIR
GAME_URL = "https://nijitama.app/switchSession/tamacolle"
CDP_PORT = 9222

STAGES = [
    # (显示名, 标题, 关键词, 副标题, 列表序号)
    # 序号是「关卡列表里第几张」，汉化后标题变中文时用它兜底定位
    ("武蔵国 江戸 火事（战场 其之四）", "武蔵国\u3000江戸\u3000火事", ["江戸", "火事"], "戦場\u3000其の四", 3),
    ("武蔵国 江戸（战场 其之三）", "武蔵国\u3000江戸", ["武蔵国", "江戸"], "戦場\u3000其の三", 4),
    ("甲斐国 笹子峠（战场 其之二）", "甲斐国\u3000笹子峠", ["甲斐国", "笹子峠"], "戦場\u3000其の二", 5),
    ("信濃国 下諏訪（战场 其之一）", "信濃国\u3000下諏訪", ["信濃国", "下諏訪"], "戦場\u3000其の一", 6),
    ("武蔵国 江戸 高難度（高难度战场 其之一）", "武蔵国\u3000江戸\u3000高難度", ["高難度"], "高難度戦場\u3000其の一", 2),
    ("甲斐国 笹子峠 高難度（高难度战场 其之二）", "甲斐国\u3000笹子峠\u3000高難度", ["高難度"], "高難度戦場\u3000其の二", 1),
    ("武蔵国 江戸（素材获得战场）", "武蔵国\u3000江戸", ["素材獲得"], "素材獲得戦場（栄養丸・雄々しい角）", 0),
]

WINDOW_PRESETS = [
    ("small", "小窗口（960 × 540）", 960, 540, False),
    ("max", "全屏（最大化）", 0, 0, True),
]

# 浏览器自身的标题栏+地址栏大约占这么高（实测 92px）
CHROME_UI_H = 92

_ICON_CACHE = {}


def svg_pixmap(name: str, size: int = 20, color: str = "#c9cdd4") -> QPixmap:
    key = (name, size, color)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    p = ASSETS / "icons" / f"{name}.svg"
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    if p.exists():
        try:
            data = p.read_text(encoding="utf-8").replace("#c9cdd4", color)
            r = QSvgRenderer(QByteArray(data.encode("utf-8")))
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.Antialiasing)
            r.render(painter, QRectF(0, 0, size, size))
            painter.end()
        except Exception:
            pass
    _ICON_CACHE[key] = pm
    return pm


def icon(name: str) -> QIcon:
    return QIcon(svg_pixmap(name, 20))


def game_day(offset_hours: int = 1) -> str:
    """
    游戏日：每天 23:00 重置，所以 23 点之后算第二天。
    """
    from datetime import datetime, timedelta
    return (datetime.now() + timedelta(hours=offset_hours)).strftime("%Y-%m-%d")


def cdp_port_open(port=CDP_PORT) -> bool:
    """
    轻量检查：只看端口通不通（本地 TCP，几微秒）。
    用来做 2 秒一次的轮询，避免每次都发 HTTP 请求卡住 UI。
    """
    s = socket.socket()
    s.settimeout(0.05)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def cdp_alive(port=CDP_PORT) -> bool:
    try:
        import json as _json
        import urllib.request as _ur
        with _ur.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.8) as r:
            data = _json.loads(r.read().decode("utf-8", "ignore"))
            return bool(data.get("webSocketDebuggerUrl"))
    except Exception:
        return False


class ConnProbe(QThread):
    """
    后台探测游戏窗口端口。
    本机连 9222 单次要 60ms 左右，放在 UI 线程里每 3 秒顿一下，
    所以丢到后台线程，结果用信号回传。
    """
    sig_result = Signal(bool)

    def __init__(self, port=CDP_PORT, parent=None):
        super().__init__(parent)
        self.port = port

    def run(self):
        try:
            self.sig_result.emit(cdp_port_open(self.port))
        except Exception:
            self.sig_result.emit(False)


class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self._on = bool(checked)
        self.setFixedSize(46, 26)
        self.setCursor(Qt.PointingHandCursor)

    def isChecked(self):
        return self._on

    def setChecked(self, v):
        if self._on != bool(v):
            self._on = bool(v)
            self.update()

    def mousePressEvent(self, e):
        self._on = not self._on
        self.update()
        self.toggled.emit(self._on)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        radius = r.height() / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#4d7cff") if self._on else QColor("#3a3d44"))
        p.drawRoundedRect(r, radius, radius)
        d = r.height() - 6
        x = r.right() - d - 3 if self._on else r.left() + 3
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))


class Card(QFrame):
    clicked = Signal()

    def __init__(self, icon_name: str, title: str, subtitle: str = "",
                 parent=None, clickable: bool = False):
        super().__init__(parent)
        self.setObjectName("Card")
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.PointingHandCursor)
            self.setStyleSheet("QFrame#Card:hover { background: #2a2d33; }")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(14)

        self.ico = QLabel()
        self.ico.setPixmap(svg_pixmap(icon_name, 22))
        self.ico.setFixedSize(26, 26)
        self.ico.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.ico)

        col = QVBoxLayout()
        col.setSpacing(3)
        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("CardTitle")
        col.addWidget(self.lbl_title)
        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setObjectName("CardSub")
        self.lbl_sub.setWordWrap(True)
        if subtitle:
            col.addWidget(self.lbl_sub)
        lay.addLayout(col, 1)

        self.right = QHBoxLayout()
        self.right.setSpacing(8)
        lay.addLayout(self.right)

    def mousePressEvent(self, e):
        if self._clickable:
            self.clicked.emit()
        super().mousePressEvent(e)

    def add_right(self, w):
        self.right.addWidget(w)
        return w


class Accordion(QFrame):
    """可点击展开/收起的卡片"""

    def __init__(self, icon_name: str, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._open = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 头部（可点击）
        self.head = QWidget()
        self.head.setCursor(Qt.PointingHandCursor)
        hl = QHBoxLayout(self.head)
        hl.setContentsMargins(16, 14, 16, 14)
        hl.setSpacing(14)

        ic = QLabel()
        ic.setPixmap(svg_pixmap(icon_name, 22))
        ic.setFixedSize(26, 26)
        ic.setAlignment(Qt.AlignCenter)
        hl.addWidget(ic)

        self.title = QLabel(title)
        self.title.setObjectName("CardTitle")
        hl.addWidget(self.title)
        hl.addStretch(1)

        self.chev = QLabel()
        self.chev.setPixmap(svg_pixmap("chevron-down", 18))
        self.chev.setFixedSize(20, 20)
        hl.addWidget(self.chev)

        outer.addWidget(self.head)

        # 内容区
        self.body = QWidget()
        bl = QVBoxLayout(self.body)
        bl.setContentsMargins(56, 0, 16, 16)
        bl.setSpacing(10)
        self.body_layout = bl
        self.body.setVisible(False)
        outer.addWidget(self.body)

        self.head.mousePressEvent = self._toggle

    def _toggle(self, e):
        self.set_open(not self._open)

    def set_open(self, v: bool):
        self._open = bool(v)
        self.body.setVisible(self._open)
        # 箭头旋转用不同图标代替
        self.chev.setPixmap(svg_pixmap("chevron-down" if self._open else "chevron-down", 18))
        self.chev.setStyleSheet("" if not self._open else "margin-top:-2px;")


    def add_layout(self, lay):
        self.body_layout.addLayout(lay)
        return lay


class Banner(QFrame):
    """顶部横幅：优先用 assets/banner.png 做背景，没有就退回渐变"""

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Banner")
        self.setMinimumHeight(186)
        self._title = title
        self._sub = subtitle
        self._pix = None
        p = ASSETS / "banner.png"
        if p.exists():
            pm = QPixmap(str(p))
            if not pm.isNull():
                self._pix = pm

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        r = self.rect()
        path = QPainterPath()
        path.addRoundedRect(QRectF(r), 12, 12)
        p.setClipPath(path)

        if self._pix is not None:
            # 等比铺满（超出裁掉），人物不变形
            scaled = self._pix.scaled(r.size(), Qt.KeepAspectRatioByExpanding,
                                      Qt.SmoothTransformation)
            dx = (r.width() - scaled.width()) // 2
            dy = (r.height() - scaled.height()) // 2
            p.drawPixmap(dx, dy, scaled)
            # 左侧压暗，标题才看得清
            ov = QLinearGradient(0, 0, r.width() * 0.75, 0)
            ov.setColorAt(0.0, QColor(0, 0, 0, 170))
            ov.setColorAt(0.45, QColor(0, 0, 0, 95))
            ov.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(r, ov)
        else:
            g = QLinearGradient(0, 0, r.width(), r.height())
            g.setColorAt(0.0, QColor("#2b3f6b"))
            g.setColorAt(0.55, QColor("#3a2f56"))
            g.setColorAt(1.0, QColor("#5b3a52"))
            p.fillRect(r, g)

        f = QFont(); f.setPointSize(20); f.setBold(True)
        p.setFont(f)
        ty = r.height() * 0.44
        p.setPen(QColor(0, 0, 0, 130))
        p.drawText(QRectF(30, ty - 15, r.width() - 60, 40),
                   Qt.AlignLeft | Qt.AlignVCenter, self._title)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(28, ty - 17, r.width() - 60, 40),
                   Qt.AlignLeft | Qt.AlignVCenter, self._title)

        if self._sub:
            f2 = QFont(); f2.setPointSize(10)
            p.setFont(f2)
            p.setPen(QColor("#e8ecf5"))
            p.drawText(QRectF(29, ty + 22, r.width() - 60, 30),
                       Qt.AlignLeft | Qt.AlignTop, self._sub)


QSS = """
QWidget { color: #d7dae0; font-size: 13px; }
QMainWindow, QWidget#Root { background: #1b1c1f; }
QWidget#Sidebar { background: #16171a; border-right: 1px solid #23252a; }
QLabel#AppTitle { color: #f0f2f5; font-size: 15px; font-weight: 600; padding: 4px 6px; }
QLabel#AppVer {
  color: #cfd6e2; font-size: 11.5px; background: #262a31;
  border: 1px solid #343a45; border-radius: 7px; padding: 2px 9px;
}

QPushButton#Nav {
  text-align: left; padding: 9px 12px; border: none; border-radius: 8px;
  color: #9aa1ad; font-size: 13.5px;
}
QPushButton#Nav:hover { background: #202226; color: #e8eaee; }
QPushButton#Nav:checked { background: #262a31; color: #ffffff; font-weight: 600; }

QFrame#Card { background: #24262b; border: 1px solid #2c2f35; border-radius: 10px; }
QLabel#CardTitle { color: #eceef2; font-size: 13.5px; }
QLabel#CardSub { color: #858c99; font-size: 11.5px; }

QFrame#Banner { border-radius: 12px; }

QPushButton#Primary {
  background: #3d6ff2; color: #ffffff; border: none; border-radius: 8px;
  padding: 9px 18px; font-size: 13px;
}
QPushButton#Primary:hover { background: #4d7cff; }
QPushButton#Primary:disabled { background: #32353b; color: #6b7280; }

QPushButton#Ghost {
  background: #2b2e34; color: #d7dae0; border: 1px solid #34383f; border-radius: 8px;
  padding: 9px 18px;
}
QPushButton#Ghost:hover { background: #33373e; }
QPushButton#Ghost:disabled { color: #6b7280; }

QComboBox, QSpinBox, QDoubleSpinBox {
  background: #1e2024; border: 1px solid #32353c; border-radius: 7px;
  padding: 6px 10px; min-height: 20px; color: #e3e6ea;
}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover { border-color: #454a53; }
QComboBox::drop-down { border: none; width: 22px; }
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 0px; border: none; }
QComboBox QAbstractItemView {
  background: #23252a; border: 1px solid #34383f; selection-background-color: #3d6ff2;
  color: #e3e6ea; outline: none;
}

QProgressBar {
  background: #33363c; border: none; border-radius: 6px; height: 12px; text-align: center;
  color: transparent;
}
QProgressBar::chunk { background: #3d6ff2; border-radius: 6px; }

QPlainTextEdit {
  background: #16171a; border: 1px solid #2c2f35; border-radius: 8px;
  color: #b9bec7; padding: 8px;
}

QLabel#State { color: #9aa1ad; font-size: 12.5px; padding: 2px; }
QLabel#Hint { font-size: 11.5px; }

QDialog { background: #1b1c1f; }
QDialog QLabel { color: #d7dae0; }

QFrame#SuppressBox {
  background: #262a31; border: 1px solid #3a414d; border-radius: 8px;
}
QCheckBox#SuppressCk { color: #eef1f5; font-size: 13px; spacing: 10px; padding: 2px; }
QCheckBox#SuppressCk::indicator {
  width: 20px; height: 20px; border: 2px solid #6b7688;
  border-radius: 5px; background: #1b1c1f;
}
QCheckBox#SuppressCk::indicator:hover { border-color: #5b8bff; }
QCheckBox#SuppressCk::indicator:checked {
  background: #4d7cff; border-color: #4d7cff;
  image: none;
}
QTextBrowser {
  background: #16171a; border: 1px solid #2c2f35; border-radius: 8px;
  color: #d7dae0; padding: 14px; font-size: 15px;
}
QTabWidget::pane { border: 1px solid #2c2f35; border-radius: 8px; top: -1px; }
QTabBar::tab {
  background: #202226; color: #9aa1ad; padding: 7px 16px; margin-right: 4px;
  border-top-left-radius: 8px; border-top-right-radius: 8px;
}
QTabBar::tab:selected { background: #2b2f36; color: #ffffff; }
QTabBar::tab:hover { color: #e8eaee; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #3a3e46; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
"""


def dir_size_mb(path) -> float:
    """目录占用（MB）"""
    try:
        total = 0
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        return total / (1024 * 1024)
    except Exception:
        return 0.0


# 可以安全删除、且不影响游戏流畅度的目录
# 注意：ShaderCache / GrShaderCache / GPUPersistentCache 故意不在列表里
#      —— 它们是显卡着色器缓存，删掉不会坏，但下次进战斗会有一小段卡顿
#      —— 而且总共才 15MB 左右，留着更划算
CLEANABLE_DIRS = [
    "Crashpad",                    # 崩溃转储
    "BrowserMetrics",              # 使用统计
    "OptGuideManifestModel",       # 端侧 AI 模型（最大头）
    "optimization_guide_model_store",
    "component_crx_cache",         # 组件下载缓存
    "SODALanguagePacks",           # 语音语言包
    "SODA",
    "WasmTtsEngine",
]


def profile_usage() -> tuple:
    """返回 (总占用 MB, [(目录名, MB), ...])"""
    prof = paths.PROFILE_DIR
    if not prof.exists():
        return 0.0, []
    total = dir_size_mb(prof)
    items = []
    for name in CLEANABLE_DIRS:
        d = prof / name
        if d.exists():
            mb = dir_size_mb(d)
            if mb > 0.05:
                items.append((name, mb))
    return total, items


def clean_profile() -> tuple:
    """清理可安全删除的缓存，返回 (释放 MB, 删掉的目录名列表)"""
    prof = paths.PROFILE_DIR
    freed = 0.0
    done = []
    for name in CLEANABLE_DIRS:
        d = prof / name
        if not d.exists():
            continue
        mb = dir_size_mb(d)
        try:
            shutil.rmtree(d, ignore_errors=True)
            if not d.exists():
                freed += mb
                done.append(name)
        except Exception:
            pass
    return freed, done


def app_icon() -> QIcon:
    """
    程序图标：把 app.ico（或 app.png）放进 assets/ 就会自动生效。
    优先级：app.ico > app.png > app.jpg > 内置 svg
    """
    for name in ("app.ico", "app.png", "app.jpg"):
        p = ASSETS / name
        if p.exists():
            ic = QIcon(str(p))
            if not ic.isNull():
                return ic
    p = ASSETS / "icons" / "gamepad-2.svg"
    if p.exists():
        return QIcon(svg_pixmap("gamepad-2", 64))
    return QIcon()


def load_doc(name: str) -> str:
    """
    读取说明文档。
    查找顺序：程序目录 → docs 子目录 → 打包内置资源。
    所以你可以把自己写的 使用说明.txt 放在 exe 旁边直接覆盖内置版。
    """
    cands = [paths.HERE / f"{name}.md", paths.HERE / f"{name}.txt",
             paths.HERE / "docs" / f"{name}.md", paths.HERE / "docs" / f"{name}.txt"]
    res = paths.resource_dir()
    if res != paths.HERE:
        cands += [res / "docs" / f"{name}.md", res / "docs" / f"{name}.txt",
                  res / f"{name}.md", res / f"{name}.txt"]
    for p in cands:
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except Exception:
                pass
    return f"（找不到说明文件：{name}）\n\n你可以自己新建一个 {name}.txt 放在程序旁边。"


class DarkMsg(QDialog):
    """
    工具箱内弹窗（替代系统 QMessageBox，保证深色主题下文字清晰）
      ask=True   -> 确定/取消，返回 bool
      ask=False  -> 只有确定
    """

    def __init__(self, parent, title: str, text: str,
                 ask=False, ok_text="确定", cancel_text="取消"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setStyleSheet(QSS)

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(14)

        head = QLabel(title)
        head.setStyleSheet("color:#f0f2f5; font-size:15px; font-weight:600;")
        v.addWidget(head)

        body = QLabel(text)
        body.setWordWrap(True)
        body.setStyleSheet("color:#b9bec7; font-size:12.5px; line-height:150%;")
        v.addWidget(body)

        row = QHBoxLayout()
        row.addStretch(1)
        if ask:
            no = QPushButton(cancel_text)
            no.setObjectName("Ghost")
            no.clicked.connect(self.reject)
            row.addWidget(no)
        ok = QPushButton(ok_text)
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        ok.setDefault(True)
        row.addWidget(ok)
        v.addLayout(row)

    @staticmethod
    def info(parent, title, text):
        DarkMsg(parent, title, text).exec()

    @staticmethod
    def warn(parent, title, text):
        DarkMsg(parent, title, text).exec()

    @staticmethod
    def confirm(parent, title, text, ok_text="退出", cancel_text="继续刷") -> bool:
        return DarkMsg(parent, title, text, ask=True,
                       ok_text=ok_text, cancel_text=cancel_text).exec() == QDialog.Accepted


class HelpOverlay(QWidget):
    """
    内置帮助面板：盖在主窗口上面，不另开窗口。
    关闭时发出 closed 信号（带「不再提示」勾选状态）。
    """
    closed = Signal(bool)     # suppress

    def __init__(self, parent, first_run=False):
        super().__init__(parent)
        self.setObjectName("Overlay")
        self.first_run = first_run
        self.suppress_checked = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 30, 40, 30)
        outer.addStretch(1)

        panel = QFrame()
        panel.setObjectName("HelpPanel")
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(18, 16, 18, 14)
        pv.setSpacing(10)

        head = QLabel("欢迎使用 · 使用说明" if first_run else "使用说明")
        head.setStyleSheet("color:#f0f2f5; font-size:16px; font-weight:600;")
        pv.addWidget(head)

        if first_run:
            tip = QLabel("第一次使用，先看一遍：① 启动游戏并登录　② 刷新关卡 → 开始刷本")
            tip.setWordWrap(True)
            tip.setStyleSheet("color:#9fc0ff; font-size:12.5px;")
            pv.addWidget(tip)

        tabs = QTabWidget()
        for title, name in (("使用说明", "使用说明"), ("功能说明", "功能说明")):
            tb = QTextBrowser()
            tb.setOpenExternalLinks(True)
            f = QFont()
            f.setPointSize(11)
            tb.setFont(f)
            tb.document().setDefaultFont(f)
            text = load_doc(name)
            if text.lstrip().startswith("#"):
                tb.setMarkdown(text)
            else:
                tb.setPlainText(text)
            tabs.addTab(tb, title)
        pv.addWidget(tabs, 1)

        row = QHBoxLayout()
        if first_run:
            box = QFrame(); box.setObjectName("SuppressBox")
            bl = QHBoxLayout(box); bl.setContentsMargins(12, 8, 12, 8)
            ck = QCheckBox("下次启动不再自动弹出")
            ck.setObjectName("SuppressCk")
            ck.setCursor(Qt.PointingHandCursor)
            ck.toggled.connect(lambda on: setattr(self, "suppress_checked", on))
            bl.addWidget(ck)
            row.addWidget(box)
        row.addStretch(1)
        close = QPushButton("稍后再说" if first_run else "关闭")
        close.setObjectName("Ghost")
        close.clicked.connect(self._close)
        row.addWidget(close)
        if first_run:
            ok = QPushButton("开始使用")
            ok.setObjectName("Primary")
            ok.clicked.connect(self._close)
            row.addWidget(ok)
        pv.addLayout(row)

        outer.addWidget(panel, 8)
        outer.addStretch(1)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 150))

    def show_overlay(self):
        parent = self.parentWidget()
        if parent:
            self.setGeometry(0, 0, parent.width(), parent.height())
        self.show()
        self.raise_()
        self.setFocus()

    def _close(self):
        self.hide()
        self.closed.emit(self.suppress_checked)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = config.load()
        self.worker = None

        self.setWindowTitle(f"{APP_NAME}  v{VERSION}")
        self.setWindowIcon(app_icon())
        self.resize(1040, 720)
        self.setStyleSheet(QSS)

        root = QWidget(); root.setObjectName("Root")
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_launch())
        self.stack.addWidget(self._page_farm())
        self.stack.addWidget(self._page_settings())
        self.stack.addWidget(self._page_log())
        lay.addWidget(self.stack, 1)

        self.setCentralWidget(root)
        self.statusBar().showMessage("就绪")
        self.nav_buttons[0].setChecked(True)
        self._ready = False          # 初始化期间不触发"回主界面"
        self._on_type_changed()
        self._ready = True

        # 连接状态自动检测（3 秒一次，只做轻量端口检查）
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_conn)
        self.timer.start(3000)
        self._refresh_conn()
        self._refresh_run_cfg()

        # 第一次使用：窗口显示后尽快弹出帮助
        QTimer.singleShot(600, self._maybe_show_help)

        # 说明文档自动留档：启动时 + 每 3 分钟检查一次内容变化
        # 这样你手动改的说明不会因为被覆盖而丢失
        try:
            import docwatch
            added = docwatch.snapshot()
            if added:
                self.append_log(f">>> 已备份说明文档 {len(added)} 个版本到 data/doc_history/")
            self.doctimer = QTimer(self)
            self.doctimer.timeout.connect(self._snapshot_docs)
            self.doctimer.start(3 * 60 * 1000)
        except Exception as e:
            self.append_log(f"!!! 文档备份不可用：{e}")

        # 每天提醒一次：曜日任務还没读（不再自动静默读取）
        QTimer.singleShot(2000, self._maybe_remind_weekday)
        self.daytimer = QTimer(self)
        self.daytimer.timeout.connect(self._maybe_remind_weekday)
        self.daytimer.start(30 * 60 * 1000)   # 每 30 分钟检查一次是否跨天

    # ---------------- 侧边栏 ----------------
    def _build_sidebar(self) -> QWidget:
        sb = QWidget(); sb.setObjectName("Sidebar")
        sb.setFixedWidth(196)
        v = QVBoxLayout(sb)
        v.setContentsMargins(12, 16, 12, 16)
        v.setSpacing(4)

        t = QLabel("にじたま 工具箱"); t.setObjectName("AppTitle")
        v.addWidget(t)
        ver_row = QHBoxLayout()
        ver_row.setContentsMargins(6, 0, 0, 0)
        ver = QLabel(f"v{VERSION}")
        ver.setObjectName("AppVer")
        ver_row.addWidget(ver)
        ver_row.addStretch(1)
        v.addLayout(ver_row)
        v.addSpacing(14)

        self.nav_buttons = []
        for i, (ic, text) in enumerate([("play", "启动游戏"), ("swords", "刷本"),
                                        ("settings", "设置"), ("scroll-text", "日志")]):
            b = QPushButton(text)
            b.setObjectName("Nav")
            b.setIcon(icon(ic))
            b.setIconSize(QSize(17, 17))
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, idx=i: self._goto(idx))
            v.addWidget(b)
            self.nav_buttons.append(b)

        v.addStretch(1)
        return sb

    def _goto(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self.nav_buttons):
            b.setChecked(i == idx)

    # ---------------- 页面1：启动游戏 ----------------
    def _page_launch(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(22, 20, 22, 20)
        v.setSpacing(14)

        v.addWidget(Banner("にじたま 工具箱", ""))

        c1 = Card("gamepad-2", "启动游戏")
        self.btn_launch = QPushButton("启动")
        self.btn_launch.setObjectName("Primary")
        self.btn_launch.clicked.connect(self.open_game)
        c1.add_right(self.btn_launch)
        v.addWidget(c1)

        # 窗口大小直接在这里选，不再跳转设置
        c2 = Card("monitor", "窗口大小")
        self.cb_win_launch = QComboBox()
        for key, name, *_r in WINDOW_PRESETS:
            self.cb_win_launch.addItem(name, key)
        self.cb_win_launch.setMinimumWidth(220)
        self.cb_win_launch.setCurrentIndex(
            0 if self.cfg.get("window_mode", "small") == "small" else 1)
        self.cb_win_launch.currentIndexChanged.connect(self._sync_window_preset)
        c2.add_right(self.cb_win_launch)
        v.addWidget(c2)

        # 当前运行设置（只读展示）
        c3 = Card("power", "当前运行设置")
        self.lbl_run_cfg = QLabel("")
        self.lbl_run_cfg.setObjectName("CardSub")
        c3.add_right(self.lbl_run_cfg)
        v.addWidget(c3)

        # 连接状态（自动刷新）
        c4 = Card("circle-dot", "游戏窗口")
        self.lbl_conn = QLabel("")
        self.lbl_conn.setObjectName("CardSub")
        c4.add_right(self.lbl_conn)
        v.addWidget(c4)

        c5 = Card("scroll-text", "帮助", "点击这里查看使用说明和功能说明", clickable=True)
        c5.clicked.connect(self.show_docs)
        chev = QLabel()
        chev.setPixmap(svg_pixmap("chevron-down", 18))
        chev.setFixedSize(20, 20)
        c5.add_right(chev)
        v.addWidget(c5)

        v.addStretch(1)
        return w

    def show_docs(self):
        self._open_help(first_run=False)

    # ---------------- 缓存清理 ----------------
    def _refresh_cache_label(self):
        """显示 profile 总占用 + 可清理的占用"""
        try:
            total, items = profile_usage()
            cleanable = sum(mb for _n, mb in items)
            if cleanable >= 1:
                self.lbl_cache.setText(
                    f"当前 {total:.0f} MB，可清理 {cleanable:.0f} MB")
            else:
                self.lbl_cache.setText(f"当前 {total:.0f} MB，已很干净")
        except Exception:
            self.lbl_cache.setText("")

    def clean_cache(self):
        """清理浏览器缓存（不动登录信息）"""
        if cdp_port_open():
            DarkMsg.info(
                self, "请先关闭游戏窗口",
                "浏览器正在运行，缓存文件被占用，清不掉。\n\n"
                "请先关掉游戏窗口，再回来点清理。")
            return
        total_before, items = profile_usage()
        if not items:
            DarkMsg.info(self, "无需清理", "当前没有可清理的缓存。")
            self._refresh_cache_label()
            return
        freed, done = clean_profile()
        self.append_log(f">>> 清理缓存：释放 {freed:.0f} MB（{', '.join(done) or '无'}）")
        self._refresh_cache_label()
        DarkMsg.info(
            self, "清理完成",
            f"释放 {freed:.0f} MB\n\n"
            f"删除了：{', '.join(done)}\n\n"
            "登录状态和游戏数据没有动。")

    def _open_help(self, first_run=False):
        """打开内置帮助面板（覆盖在主窗口上，不另开窗口）"""
        if getattr(self, "_help", None) is not None:
            try:
                self._help.deleteLater()
            except Exception:
                pass
        self._help = HelpOverlay(self, first_run=first_run)
        self._help.closed.connect(
            lambda sup: self._on_help_closed(sup, first_run))
        self._help.show_overlay()
        self.append_log(">>> 帮助面板已打开（看完点「开始使用」或按 Esc 关闭）")
        # 如果没显示出来（窗口还没就绪），300ms 后再试一次
        QTimer.singleShot(300, self._ensure_help_visible)

    def _ensure_help_visible(self):
        ov = getattr(self, "_help", None)
        if ov is None:
            return
        if not ov.isVisible() and not getattr(self, "_help_closed_once", False):
            self.append_log(">>> 帮助面板未显示，重试")
            ov.show_overlay()

    def _on_help_closed(self, suppress, first_run):
        self._help_closed_once = True
        self.append_log(f">>> 帮助面板已关闭（不再提示={suppress}）")
        if first_run:
            if suppress:
                self.cfg["show_help_on_start"] = False
                config.save(self.cfg)
                self.append_log(">>> 已关闭启动时自动显示帮助（随时可在【帮助】里打开）")
            else:
                self.append_log(">>> 下次启动仍会显示帮助（可在面板里勾选不再提示）")
        try:
            self._help.deleteLater()
            self._help = None
        except Exception:
            pass

    def _snapshot_docs(self):
        """定时检查说明文档是否被改过，改过就留一份历史"""
        try:
            import docwatch
            for item in docwatch.snapshot():
                self.append_log(
                    f">>> 说明文档有变化，已存档：{item['name']}"
                    f"（{item['size']} 字，{item['hash']}）")
        except Exception:
            pass

    def _maybe_show_help(self):
        """第一次使用自动弹出帮助；勾选「不再提示」后不再弹"""
        if not self.cfg.get("show_help_on_start", True):
            self.append_log(">>> 启动帮助已设为不再弹出（可在【帮助】里手动打开）")
            return
        if not self.isVisible() or self.isMinimized():
            self.append_log(">>> 窗口还没就绪，1 秒后再弹帮助")
            QTimer.singleShot(1000, self._maybe_show_help)
            return
        self._help_closed_once = False
        self._open_help(first_run=True)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        ov = getattr(self, "_help", None)
        if ov is not None and ov.isVisible():
            ov.setGeometry(0, 0, self.width(), self.height())

    # ---------------- 页面2：刷本 ----------------
    def _page_farm(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(22, 20, 22, 20)
        v.setSpacing(14)

        head = QLabel("刷本")
        head.setStyleSheet("color:#f0f2f5; font-size:18px; font-weight:600;")
        v.addWidget(head)

        # 运行模式（可展开/收起，完成后并入其中）
        self.acc_mode = Accordion("swords", "运行模式")
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("模式"))
        self.cb_mode = QComboBox()
        self.cb_mode.addItem("一条龙", "oneclick")
        self.cb_mode.addItem("普通", "attach")
        self.cb_mode.setMinimumWidth(180)
        self.cb_mode.setCurrentIndex(0 if self.cfg.get("mode") == "oneclick" else 1)
        row1.addWidget(self.cb_mode)
        row1.addStretch(1)
        self.acc_mode.add_layout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("完成后"))
        self.cb_after = QComboBox()
        self.cb_after.addItem("留在游戏里", "keep")
        self.cb_after.addItem("关闭游戏窗口", "close")
        self.cb_after.setMinimumWidth(180)
        self.cb_after.setCurrentIndex(0 if self.cfg.get("after") == "keep" else 1)
        row2.addWidget(self.cb_after)
        row2.addStretch(1)
        self.acc_mode.add_layout(row2)

        self.cb_mode.currentIndexChanged.connect(self._on_mode_changed)
        self.cb_after.currentIndexChanged.connect(lambda _i: self._refresh_mode_title())
        self._refresh_mode_title()
        v.addWidget(self.acc_mode)

        # 任务设置
        c3 = Card("gamepad-2", "任务设置")
        col = QVBoxLayout(); col.setSpacing(8)

        row0 = QHBoxLayout()
        self.cb_type = QComboBox()
        self.cb_type.addItem("净化巡历", "junreki")
        self.cb_type.addItem("曜日任務", "weekday")
        self.cb_type.setMinimumWidth(150)
        self.cb_type.setCurrentIndex(
            0 if self.cfg.get("stage_type", "junreki") == "junreki" else 1)
        self.cb_type.currentIndexChanged.connect(self._on_type_changed)
        row0.addWidget(QLabel("副本类型")); row0.addWidget(self.cb_type)
        row0.addStretch(1)
        col.addLayout(row0)

        row1 = QHBoxLayout()
        self.cb_stage = QComboBox()
        self.cb_stage.setMinimumWidth(340)
        row1.addWidget(QLabel("目标关卡")); row1.addWidget(self.cb_stage, 1)
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setObjectName("Ghost")
        self.btn_refresh.setFixedWidth(72)
        self.btn_refresh.clicked.connect(self.refresh_stages)
        row1.addWidget(self.btn_refresh)
        col.addLayout(row1)

        row2 = QHBoxLayout()
        self.sp_runs = QSpinBox(); self.sp_runs.setRange(0, 9999)
        self.sp_runs.setFixedWidth(88)
        self.sp_runs.setValue(int(self.cfg.get("runs", 5)))
        self.sp_runs.setSpecialValueText("无限")
        self.sp_interval = QDoubleSpinBox(); self.sp_interval.setRange(0, 120)
        self.sp_interval.setSingleStep(0.5)
        self.sp_interval.setFixedWidth(96)
        self.sp_interval.setValue(float(self.cfg.get("interval", 2.0)))
        row2.addWidget(QLabel("刷本次数")); row2.addWidget(self.sp_runs)
        row2.addSpacing(16)
        row2.addWidget(QLabel("间隔(秒)")); row2.addWidget(self.sp_interval)
        row2.addStretch(1)
        col.addLayout(row2)
        c3.right.addLayout(col)
        v.addWidget(c3)

        ctl = QHBoxLayout()
        self.btn_start = QPushButton("开始刷本")
        self.btn_start.setObjectName("Primary")
        self.btn_start.setMinimumHeight(38)
        self.btn_start.clicked.connect(self.on_start)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setObjectName("Ghost")
        self.btn_stop.setMinimumHeight(38)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.on_stop)
        ctl.addWidget(self.btn_start, 2)
        ctl.addWidget(self.btn_stop, 1)
        v.addLayout(ctl)

        self.progress = QProgressBar()
        self.progress.setFixedHeight(12)
        self.progress.setTextVisible(False)
        self.progress.setValue(0)
        v.addWidget(self.progress)

        self.lbl_state = QLabel("未开始")
        self.lbl_state.setObjectName("State")
        v.addWidget(self.lbl_state)
        v.addStretch(1)
        return w

    # ---------------- 页面3：设置 ----------------
    def _page_settings(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(22, 20, 22, 20)
        v.setSpacing(14)

        head = QLabel("设置")
        head.setStyleSheet("color:#f0f2f5; font-size:18px; font-weight:600;")
        v.addWidget(head)

        c1 = Card("monitor", "窗口大小")
        self.cb_win_set = QComboBox()
        for key, name, *_r in WINDOW_PRESETS:
            self.cb_win_set.addItem(name, key)
        self.cb_win_set.setMinimumWidth(220)
        self.cb_win_set.setCurrentIndex(
            0 if self.cfg.get("window_mode", "small") == "small" else 1)
        self.cb_win_set.currentIndexChanged.connect(self._sync_window_preset)
        c1.add_right(self.cb_win_set)
        v.addWidget(c1)

        c2 = Card("power", "启动时打开声音")
        self.sw_sound = ToggleSwitch(bool(self.cfg.get("sound", True)))
        self.sw_sound.toggled.connect(lambda _v: self._refresh_run_cfg())
        c2.add_right(self.sw_sound)
        v.addWidget(c2)

        c3 = Card("gamepad-2", "无头模式")
        self.sw_headless = ToggleSwitch(bool(self.cfg.get("headless", False)))
        self.sw_headless.toggled.connect(lambda _v: self._refresh_run_cfg())
        c3.add_right(self.sw_headless)
        v.addWidget(c3)

        c4 = Card("settings", "显卡渲染")
        self.sw_gpu = ToggleSwitch(bool(self.cfg.get("gpu", True)))
        c4.add_right(self.sw_gpu)
        v.addWidget(c4)

        # 清理浏览器缓存（AI 模型、语言包、崩溃日志等占空间的东西）
        self.card_clean = Card("power", "清理浏览器缓存")
        self.lbl_cache = QLabel("")
        self.lbl_cache.setObjectName("CardSub")
        self.card_clean.add_right(self.lbl_cache)
        self.btn_clean = QPushButton("清理")
        self.btn_clean.setObjectName("Ghost")
        self.btn_clean.clicked.connect(self.clean_cache)
        self.card_clean.add_right(self.btn_clean)
        v.addWidget(self.card_clean)
        QTimer.singleShot(50, self._refresh_cache_label)

        save = QPushButton("保存设置")
        save.setObjectName("Primary")
        save.clicked.connect(self.save_settings)
        row = QHBoxLayout(); row.addWidget(save); row.addStretch(1)
        v.addLayout(row)
        v.addStretch(1)
        return w

    # ---------------- 页面4：日志 ----------------
    def _page_log(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(22, 20, 22, 20)
        v.setSpacing(12)

        head = QLabel("日志")
        head.setStyleSheet("color:#f0f2f5; font-size:18px; font-weight:600;")
        v.addWidget(head)

        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumBlockCount(5000)
        f = QFont("Consolas"); f.setPointSize(9)
        self.txt_log.setFont(f)
        v.addWidget(self.txt_log, 1)

        row = QHBoxLayout()
        b1 = QPushButton("清空"); b1.setObjectName("Ghost")
        b1.clicked.connect(lambda: self.txt_log.clear())
        b2 = QPushButton("复制全部"); b2.setObjectName("Ghost")
        b2.clicked.connect(self._copy_log)
        b3 = QPushButton("错误日志"); b3.setObjectName("Ghost")
        b3.setToolTip("打开 data/error.log（程序出错时自动记录）")
        b3.clicked.connect(self._open_error_log)
        row.addWidget(b1); row.addWidget(b2); row.addWidget(b3)
        row.addStretch(1)
        v.addLayout(row)
        return w

    def _open_error_log(self):
        p = paths.DATA_DIR / "error.log"
        if not p.exists():
            DarkMsg.info(self, "没有错误记录", "程序还没有记录到异常。")
            return
        try:
            os.startfile(str(p))
        except Exception as e:
            DarkMsg.warn(self, "打不开", f"{e}\n\n文件位置：\n{p}")

    # ---------------- 行为 ----------------
    def _refresh_mode_title(self):
        if not hasattr(self, "acc_mode"):
            return
        self.acc_mode.title.setText(
            f"运行模式 · {self.cb_mode.currentText()} · {self.cb_after.currentText()}")

    def _on_type_changed(self, *_):
        """切换副本类型：净化巡历用内置全关卡；曜日任務用当天读到的列表"""
        is_weekday = self.cb_type.currentData() == "weekday"
        # 刷新只给曜日任務用（净化巡历已内置全部关卡）
        self.btn_refresh.setVisible(is_weekday)
        if is_weekday:
            self._fill_weekday_stages()
        else:
            self._fill_junreki_stages()
        self._ensure_home_after_switch("副本类型")

    def _fill_weekday_stages(self):
        """用配置里缓存的当日关卡填下拉框"""
        self.cb_stage.clear()
        stages = self.cfg.get("weekday_stages") or []
        fresh = (self.cfg.get("weekday_day") == game_day())
        saved_title = self.cfg.get("stage_title_weekday", "")
        if stages and fresh:
            for s in stages:
                title = s.get("title", "")
                sub = s.get("sub", "")
                cidx = s.get("idx")
                text = f"{title}　{sub}" if sub else title
                self.cb_stage.addItem(text, (title, sub, cidx))
            for i in range(self.cb_stage.count()):
                if (self.cb_stage.itemData(i) or ("", ""))[0] == saved_title:
                    self.cb_stage.setCurrentIndex(i)
                    break
        else:
            hint = "（今天还没刷新，点「刷新」读取）" if not stages else "（已过期，点「刷新」读取今日关卡）"
            self.cb_stage.addItem(hint, ("", ""))

    def _fill_junreki_stages(self):
        """净化巡历：内置「はじまりの旅」一页的全部关卡"""
        self.cb_stage.blockSignals(True)
        self.cb_stage.clear()
        for name, t, _k, sub, cidx in STAGES:
            self.cb_stage.addItem(name, (t, sub, cidx))
        saved = self.cfg.get("stage_title", "")
        for i in range(self.cb_stage.count()):
            if (self.cb_stage.itemData(i) or ("", ""))[0] == saved:
                self.cb_stage.setCurrentIndex(i)
                break
        self.cb_stage.blockSignals(False)

    def refresh_stages(self):
        """读取当前副本类型的关卡列表（需要已连接的游戏窗口）"""
        if not cdp_alive():
            DarkMsg.info(
                self, "需要先打开游戏",
                "读取关卡列表需要连上游戏：\n"
                "先到【启动游戏】点「启动」，等画面出来后回来点「刷新」。")
            return
        kind = "weekday" if self.cb_type.currentData() == "weekday" else "junreki"
        from worker import ListWorker
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("读取中")
        self.append_log(">>> 正在读取%s关卡…" % ("曜日任務" if kind == "weekday" else "净化巡历"))

        self.lw = ListWorker(self.cfg, kind, self)
        self.lw.sig_done.connect(self._on_list_done)
        self.lw.start()

    def _on_list_done(self, cards, err):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("刷新")
        if err:
            self.append_log(f"!!! 读取失败：{err}")
            DarkMsg.warn(self, "读取失败", err)
            return

        kind = getattr(self.lw, "kind", "weekday")
        data = [{"title": c["title"], "sub": c.get("sub", ""),
                 "idx": c.get("idx", i)} for i, c in enumerate(cards)]
        if kind == "weekday":
            self.cfg["weekday_stages"] = data
            self.cfg["weekday_day"] = game_day()
        else:
            # 净化巡历永久保存，不设过期
            self.cfg["junreki_stages"] = data
        config.save(self.cfg)

        self.cb_stage.clear()
        for i, c in enumerate(cards):
            title = c.get("title", "")
            sub = c.get("sub", "")
            text = f"{title}　{sub}" if sub else title
            self.cb_stage.addItem(text, (title, sub, c.get("idx", i)))
        saved = (self.cfg.get("stage_title_weekday", "") if kind == "weekday"
                 else self.cfg.get("stage_title", ""))
        for i in range(self.cb_stage.count()):
            if (self.cb_stage.itemData(i) or ("", ""))[0] == saved:
                self.cb_stage.setCurrentIndex(i)
                break
        extra = f"（{game_day()} 有效）" if kind == "weekday" else "（已永久保存）"
        self.append_log(f">>> 读取到 {len(cards)} 个关卡{extra}")

    def _on_mode_changed(self, *_):
        self._refresh_mode_title()
        self._ensure_home_after_switch("运行模式")

    def _ensure_home_after_switch(self, reason: str):
        """
        切换模式/副本类型后，确保游戏回到主界面。
        否则游戏可能停在编队/报告书/章末界面，直接开刷会定位失败。
        """
        if not getattr(self, "_ready", False):
            return
        if self.worker and self.worker.isRunning():
            return
        if not cdp_alive():
            return
        self.append_log(f">>> {reason}已切换，把游戏带回主界面…")
        from worker import HomeWorker
        self.hw = HomeWorker(self.cfg, self)
        self.hw.sig_done.connect(
            lambda ok, msg: self.append_log(
                ">>> 已回到主界面" if ok else f"!!! 未能回到主界面：{msg}"))
        self.hw.start()

    def _maybe_remind_weekday(self):
        """
        每天提醒一次：曜日任務的关卡列表还没读。
        不再自动静默读取，改成弹窗问用户。
        """
        today = game_day()
        if self.cfg.get("weekday_day") == today:
            return                      # 今天已经读过了
        if self.cfg.get("weekday_remind_day") == today:
            return                      # 今天已经提醒过了
        if self.worker and self.worker.isRunning():
            return                      # 正在刷本，别打扰

        # 记下"今天提醒过"，避免每次启动都弹
        self.cfg["weekday_remind_day"] = today
        config.save(self.cfg)

        go = DarkMsg.confirm(
            self, "曜日任務还没刷新",
            f"今天是新的游戏日（{today}），曜日任務的关卡列表还没读取。\n\n"
            "现在去读吗？\n\n"
            "· 读之前请先把游戏打开并进入主界面\n"
            "· 也可以稍后在【刷本】页手动点「刷新」",
            ok_text="现在读取", cancel_text="稍后再说")
        if not go:
            self.append_log(">>> 已推迟曜日任務刷新（稍后可在【刷本】页点「刷新」）")
            return

        if not cdp_alive():
            DarkMsg.info(
                self, "还没有游戏窗口",
                "读取关卡需要连上游戏：\n\n"
                "1. 到【启动游戏】点「启动」\n"
                "2. 等游戏进入主界面\n"
                "3. 回来点【刷本】页的「刷新」")
            self.append_log(">>> 想读取曜日任務，但游戏没打开")
            return

        self.append_log(">>> 按提醒刷新曜日任務…")
        self.refresh_stages()

    def _current_stage(self, is_weekday=None):
        if is_weekday is None:
            is_weekday = self.cb_type.currentData() == "weekday"
        data = self.cb_stage.currentData()
        if isinstance(data, (tuple, list)) and len(data) >= 2:
            title, sub = data[0], data[1]
            cidx = data[2] if len(data) > 2 else None
        else:
            title, sub, cidx = (data or ""), "", None
        if is_weekday:
            return self.cb_stage.currentText(), title, [], sub, cidx
        # 净化巡历：关键词从标题里拆（例如 武蔵国　江戸　火事 -> 江戸, 火事）
        parts = [p for p in str(title).replace("\u3000", " ").split(" ") if p]
        keywords = parts[1:] if len(parts) > 1 else parts
        return self.cb_stage.currentText(), title, keywords, sub, cidx

    def _preset(self):
        key = self.cb_win_launch.currentData()
        for k, name, w_, h_, m_ in WINDOW_PRESETS:
            if k == key:
                return k, w_, h_, m_
        return "small", 960, 540, False

    def _sync_window_preset(self, *_):
        src = self.sender()
        other = self.cb_win_set if src is self.cb_win_launch else self.cb_win_launch
        key = self._preset()[0] if src is self.cb_win_launch else self.cb_win_set.currentData()
        for i in range(other.count()):
            if other.itemData(i) == key:
                other.blockSignals(True)
                other.setCurrentIndex(i)
                other.blockSignals(False)
                break
        self._refresh_run_cfg()

    def _sound_effective(self) -> bool:
        """无头模式强制静音"""
        return bool(self.sw_sound.isChecked()) and not self.sw_headless.isChecked()

    def _refresh_run_cfg(self):
        if not hasattr(self, "lbl_run_cfg"):
            return
        win = self.cb_win_launch.currentText()
        sound = "声音开" if self._sound_effective() else "静音"
        head = "无头" if self.sw_headless.isChecked() else "有窗口"
        self.lbl_run_cfg.setText(f"{win} · {sound} · {head}")

    def _refresh_conn(self):
        """
        连接状态轮询：探测放到后台线程，UI 线程完全不被阻塞。
        并且只在状态变化时才改文字/样式（重设样式表很贵）。
        """
        if not hasattr(self, "lbl_conn"):
            return
        probe = getattr(self, "_probe", None)
        if probe is not None and probe.isRunning():
            return
        self._probe = ConnProbe(CDP_PORT, self)
        self._probe.sig_result.connect(self._on_conn_result)
        self._probe.start()

    def _on_conn_result(self, ok: bool):
        if ok == getattr(self, "_conn_state", None):
            return
        self._conn_state = ok
        if ok:
            self.lbl_conn.setText("● 已连接")
            self.lbl_conn.setStyleSheet("color:#5fbf7f; font-size:11.5px;")
        else:
            self.lbl_conn.setText("○ 未检测到")
            self.lbl_conn.setStyleSheet("color:#7c828d; font-size:11.5px;")

    def append_log(self, text: str):
        self.txt_log.appendPlainText(text)
        self.txt_log.moveCursor(QTextCursor.End)

    def _copy_log(self):
        QApplication.clipboard().setText(self.txt_log.toPlainText())
        self.statusBar().showMessage("日志已复制", 3000)

    def _collect_cfg(self):
        key, w_, h_, maximized = self._preset()
        is_weekday = self.cb_type.currentData() == "weekday"
        name, title, kw, sub, cidx = self._current_stage(is_weekday)
        self.cfg.update({
            "stage_type": "weekday" if is_weekday else "junreki",
            "stage_title": title, "stage_keywords": kw, "stage_sub": sub,
            "stage_idx": cidx,
            "runs": self.sp_runs.value(), "interval": self.sp_interval.value(),
            "mode": self.cb_mode.currentData(), "after": self.cb_after.currentData(),
            "window_mode": key, "width": w_, "height": h_, "maximized": maximized,
            "headless": self.sw_headless.isChecked(),
            "sound": self.sw_sound.isChecked(),
            "gpu": self.sw_gpu.isChecked(),
        })
        if is_weekday:
            self.cfg["stage_title_weekday"] = title
        return name

    def save_settings(self):
        self._collect_cfg()
        config.save(self.cfg)
        self._refresh_run_cfg()
        self.statusBar().showMessage("设置已保存", 3000)

    def open_game(self):
        from gamebot import find_chrome
        exe = find_chrome()
        if not exe:
            DarkMsg.warn(self, "找不到浏览器", "需要系统里装有 Chrome 或 Edge。")
            return
        if cdp_alive():
            self.statusBar().showMessage("游戏窗口已经在运行了", 4000)
            self._refresh_conn()
            return
        key, w_, h_, maximized = self._preset()
        profile = str(HERE / "profile")
        args = [
            "--no-sandbox", "--no-first-run", "--no-default-browser-check",
            # 关掉 Chrome 的端侧 AI 模型下载与组件更新（会吃掉几 GB 磁盘）
            "--disable-features=OptimizationGuideModelDownloading,OptimizationHints",
            "--disable-component-update",
            f"--user-data-dir={profile}",
            f"--remote-debugging-port={CDP_PORT}",
            "--ignore-gpu-blocklist", "--enable-gpu", "--use-angle=d3d11",
        ]
        if maximized:
            args.append("--start-maximized")
        else:
            args += [f"--window-size={w_},{h_ + CHROME_UI_H}", "--window-position=120,40"]
        if not self._sound_effective():
            args.append("--mute-audio")
        args.append(GAME_URL)
        try:
            paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
            self._chrome_log = paths.DATA_DIR / "chrome_start.log"
            lf = open(self._chrome_log, "wb")
            subprocess.Popen([exe] + args,
                             creationflags=0x00000008 | 0x00000200,
                             stdout=lf, stderr=subprocess.STDOUT,
                             close_fds=True)
            lf.close()
            self.append_log(f">>> 启动命令: {exe}")
            self.append_log("    " + " ".join(args))
        except Exception as e:
            DarkMsg.warn(self, "打开失败", f"无法启动浏览器：\n{e}")
            return

        # 不能立刻说成功：等调试端口真的起来
        self.append_log(f">>> 正在启动游戏窗口（{key}"
                        f"{'，静音' if not self._sound_effective() else ''}）")
        self.btn_launch.setEnabled(False)
        self.btn_launch.setText("启动中")
        self._launch_deadline = time.time() + 45
        self._poll_launch()

    def _poll_launch(self):
        """轮询等待浏览器调试端口就绪"""
        if cdp_alive():
            self.btn_launch.setEnabled(True)
            self.btn_launch.setText("启动")
            self.append_log(">>> 游戏窗口已就绪")
            self.statusBar().showMessage("游戏窗口已启动", 5000)
            self._refresh_conn()
            return
        if time.time() > getattr(self, "_launch_deadline", 0):
            self.btn_launch.setEnabled(True)
            self.btn_launch.setText("启动")
            self.append_log("!!! 浏览器没有起来（调试端口未就绪）")
            detail = ""
            try:
                log_p = getattr(self, "_chrome_log", None)
                if log_p and Path(log_p).exists():
                    lines = Path(log_p).read_text(
                        encoding="utf-8", errors="ignore").strip().splitlines()
                    if lines:
                        detail = "\n\n----- Chrome 输出（最后几行）-----\n" + \
                                 "\n".join(lines[-6:])
                        self.append_log("\n".join(lines[-6:]))
            except Exception:
                pass
            DarkMsg.warn(
                self, "启动失败",
                "浏览器没能启动。常见原因：\n\n"
                "1. 已经有一个游戏窗口在使用同一份配置目录\n"
                "   → 先把它关掉再试\n"
                "2. Chrome 被安全软件拦住了\n"
                f"\n日志文件：data\\chrome_start.log{detail}")
            return
        QTimer.singleShot(500, self._poll_launch)

    def on_start(self):
        from worker import BotWorker

        if self.cb_mode.currentData() == "attach" and not cdp_alive():
            DarkMsg.info(
                self, "还没有游戏窗口",
                "普通模式需要先打开游戏：\n"
                "1. 到【启动游戏】点「启动」\n"
                "2. 等游戏画面出来\n"
                "3. 回来点「开始刷本」\n\n"
                "或把模式改成【一条龙】，它会自动打开。")
            return

        name = self._collect_cfg()
        config.save(self.cfg)

        target = self.cfg["runs"] or 1
        self.progress.setMaximum(max(target, 1))
        self.progress.setValue(0)
        self.lbl_state.setText("启动中…")

        self.worker = BotWorker(self.cfg, self)
        self.worker.sig_log.connect(self.append_log)
        self.worker.sig_status.connect(
            lambda s: (self.lbl_state.setText(s), self.statusBar().showMessage(s)))
        self.worker.sig_progress.connect(self._on_progress)
        self.worker.sig_done.connect(self._on_done)
        self.worker.start()

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.append_log(f"===== 开始（{self.cb_mode.currentText()}）：{name} =====")
        # 开始刷本后自动最小化，不挡着游戏窗口
        QTimer.singleShot(300, self.showMinimized)

    def _on_progress(self, cur, total):
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(cur)

    def _on_done(self, summary, done):
        self.lbl_state.setText(summary)
        self.append_log(f"===== {summary} =====")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress.setValue(done)
        self._refresh_conn()

    def on_stop(self):
        if self.worker and self.worker.isRunning():
            self.append_log(">>> 正在停止（战斗会立即中断）…")
            self.lbl_state.setText("正在停止…")
            self.worker.request_stop()
            self.btn_stop.setEnabled(False)
            self.statusBar().showMessage("正在停止…", 5000)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            if not DarkMsg.confirm(self, "确认退出", "刷本还在运行，确定退出吗？"):
                event.ignore()
                return
            self.worker.request_stop()
            # 最多等 6 秒，超时就直接放弃（浏览器是独立进程，不会被带崩）
            if not self.worker.wait(6000):
                self.append_log(">>> 后台线程未在 6 秒内退出，强制结束")
                self.worker.terminate()
                self.worker.wait(2000)
        self._collect_cfg()
        config.save(self.cfg)
        probe = getattr(self, "_probe", None)
        if probe is not None and probe.isRunning():
            probe.wait(1500)
        event.accept()


def _win32_foreground(win):
    """
    用 Win32 强制抢前台。
    Qt 的 raise_/activateWindow 在 Windows 上经常被系统忽略（焦点还给别的程序），
    这里直接调 SetForegroundWindow 更可靠。
    """
    try:
        import ctypes
        hwnd = int(win.winId())
        u = ctypes.windll.user32
        u.AllowSetForegroundWindow(-1)      # ASFW_ANY
        u.ShowWindow(hwnd, 9)               # SW_RESTORE
        u.BringWindowToTop(hwnd)
        u.SetForegroundWindow(hwnd)
    except Exception:
        pass


def _win32_topmost(win, on: bool):
    """
    调整窗口置顶状态。
    不用 Qt 的 setWindowFlag —— 那会销毁并重建原生窗口，界面会闪一下；
    SetWindowPos 是原地调整，不会闪。
    """
    try:
        import ctypes
        hwnd = int(win.winId())
        SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
        hwnd_insert = -1 if on else -2       # HWND_TOPMOST / HWND_NOTOPMOST
        ctypes.windll.user32.SetWindowPos(
            hwnd, hwnd_insert, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    except Exception:
        pass


def bring_to_front(win, force_top=True):
    """把窗口拉到最前面（不重建窗口，避免闪烁）"""
    try:
        if win.isMinimized():
            win.setWindowState(win.windowState() & ~Qt.WindowMinimized)
        if not win.isVisible():
            win.show()
        if force_top:
            _win32_topmost(win, True)
        win.raise_()
        win.activateWindow()
    except Exception:
        pass
    _win32_foreground(win)


def _unpin(win):
    _win32_topmost(win, False)


def install_error_handler(get_window):
    """
    全局异常捕获。
    程序用 pythonw 启动时没有控制台，异常会被静默吞掉，
    表现为「点了没反应」。这里统一写入 data/error.log 并在界面提示。
    """
    import threading
    import traceback

    def write_log(kind, text):
        try:
            paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
            p = paths.DATA_DIR / "error.log"
            with open(p, "a", encoding="utf-8") as f:
                f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} [{kind}] =====\n{text}")
        except Exception:
            pass

    def show(text, exc):
        win = get_window()
        if win is None:
            return
        try:
            win.append_log(f"!!! 程序异常：{exc}")
            win.append_log(f"    详情已写入 data/error.log")
        except Exception:
            pass
        try:
            DarkMsg.warn(win, "出错了",
                         f"{type(exc).__name__}: {exc}\n\n"
                         f"详细信息已写入 data/error.log\n"
                         f"可以把文件发给开发者排查。")
        except Exception:
            pass

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        write_log("main", text)
        show(text, exc)
        try:
            sys.__excepthook__(exc_type, exc, tb)
        except Exception:
            pass

    def thread_hook(args):
        text = "".join(traceback.format_exception(
            args.exc_type, args.exc_value, args.exc_traceback))
        write_log(f"thread:{getattr(args.thread, 'name', '?')}", text)
        show(text, args.exc_value)

    sys.excepthook = hook
    try:
        threading.excepthook = thread_hook
    except Exception:
        pass


def main():
    # 让 Windows 把本程序当成独立应用，而不是 pythonw.exe 的子进程
    # 否则任务栏会显示 Python 的图标、分组也不对
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "nijitama.toolbox.app")
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("にじたま 工具箱")
    ic = app_icon()
    if not ic.isNull():
        app.setWindowIcon(ic)      # 让所有窗口/对话框都用这个图标
    win = MainWindow()
    # 装全局异常捕获：pythonw 没有控制台，异常必须写文件+弹提示
    install_error_handler(lambda: win)
    if not ic.isNull():
        win.setWindowIcon(ic)      # 标题栏 + 任务栏
    bring_to_front(win)
    # 临时置顶 2.5 秒再取消：足够让用户看到窗口弹出来
    QTimer.singleShot(2500, lambda: _unpin(win))
    QTimer.singleShot(150, lambda: bring_to_front(win, force_top=False))
    QTimer.singleShot(600, lambda: bring_to_front(win, force_top=False))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
