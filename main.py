"""CAN Bus Parser GUI — main entry point."""

import os
import sys
import tempfile

from PyQt5.QtCore import QPointF, QSize, Qt, QTimer
from PyQt5.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QToolBar,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from can_backend import CanBackend
from dbc_loader import DbcLoader
from live_view import LiveView
from log_view import LogView

STYLESHEET = """
/* ── Global ── */
QMainWindow { background-color: #0d1117; }
QWidget#mainWrapper { background-color: #0d1117; }
QLabel { color: #e6edf3; font-size: 12px; }

/* ── Title bar ── */
#titleBar {
    background-color: #161b22;
    border-bottom: 1px solid #21262d;
}
#titleLabel {
    color: #e6edf3; font-size: 13px; font-weight: 600;
    padding-left: 6px; letter-spacing: 0.4px;
}
QPushButton#titleBtn, QPushButton#titleClose {
    background-color: transparent;
    border: none; border-radius: 0px; padding: 0px;
}
QPushButton#titleBtn:hover { background-color: #21262d; }
QPushButton#titleBtn:pressed { background-color: #30363d; }
QPushButton#titleClose:hover { background-color: #da3633; }
QPushButton#titleClose:pressed { background-color: #b62324; }

/* ── Toolbar ── */
QToolBar {
    background-color: #161b22; border: none;
    border-bottom: 1px solid #21262d;
    padding: 6px 10px; spacing: 8px;
}
QToolBar::separator { width: 1px; background-color: #30363d; margin: 5px 6px; }
QToolBar QLabel { color: #8b949e; font-size: 12px; font-weight: 600; }

/* ── Text inputs ── */
QLineEdit {
    background-color: #0d1117; color: #e6edf3;
    border: 1px solid #30363d; border-radius: 6px;
    padding: 5px 10px; font-size: 12px;
    selection-background-color: #1f6feb; selection-color: #ffffff;
}
QLineEdit:hover { border-color: #484f58; }
QLineEdit:focus { border-color: #58a6ff; }
QLineEdit:disabled { background-color: #161b22; color: #484f58; border-color: #21262d; }

/* ── Combo box (button-like) ── */
QComboBox {
    background-color: #21262d; color: #e6edf3;
    border: 1px solid #30363d; border-radius: 6px;
    padding: 4px 28px 4px 10px; font-size: 12px; font-weight: 600;
    min-width: 90px;
}
QComboBox:hover { background-color: #30363d; border-color: #8b949e; }
QComboBox:on { background-color: #161b22; border-color: #58a6ff; }
QComboBox:focus { border-color: #58a6ff; }
QComboBox:disabled { background-color: #161b22; color: #484f58; border-color: #21262d; }
QComboBox::drop-down {
    subcontrol-origin: padding; subcontrol-position: top right;
    width: 24px; border: none;
}
QComboBox::down-arrow { image: url(@chevron_down@); width: 10px; height: 6px; }
QComboBox::down-arrow:disabled { image: url(@chevron_down_dim@); }
QComboBox QAbstractItemView {
    background-color: #161b22; color: #e6edf3;
    border: 1px solid #30363d; padding: 4px; outline: none;
    selection-background-color: #1f6feb; selection-color: #ffffff;
}
QComboBox QAbstractItemView::item { min-height: 26px; padding: 0px 10px; border-radius: 4px; }
QComboBox QAbstractItemView::item:hover { background-color: #21262d; }
QComboBox QAbstractItemView::item:selected { background-color: #1f6feb; color: #ffffff; }

/* ── Push buttons ── */
QPushButton {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 #272d35, stop:1 #21262d);
    color: #e6edf3;
    border: 1px solid #30363d; border-radius: 6px;
    padding: 5px 14px; font-size: 12px; font-weight: 600;
}
QPushButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 #30363d, stop:1 #2a3139);
    border-color: #8b949e;
}
QPushButton:pressed { background-color: #161b22; border-color: #30363d; }
QPushButton:disabled { background-color: #161b22; color: #484f58; border-color: #21262d; }

QPushButton#startBtn {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 #2ea043, stop:1 #238636);
    color: #ffffff; border: 1px solid #2ea043;
    padding: 5px 16px; font-weight: 700;
}
QPushButton#startBtn:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 #3fb950, stop:1 #2ea043);
    border-color: #3fb950;
}
QPushButton#startBtn:pressed { background-color: #196c2e; }
QPushButton#startBtn:disabled { background-color: #161b22; color: #484f58; border-color: #21262d; }

QPushButton#stopBtn {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 #f85149, stop:1 #da3633);
    color: #ffffff; border: 1px solid #f85149;
    padding: 5px 16px; font-weight: 700;
}
QPushButton#stopBtn:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 #ff7b72, stop:1 #f85149);
    border-color: #ff7b72;
}
QPushButton#stopBtn:pressed { background-color: #b62324; }
QPushButton#stopBtn:disabled { background-color: #161b22; color: #484f58; border-color: #21262d; }

QPushButton#parseBtn {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 #388bfd, stop:1 #1f6feb);
    color: #ffffff; border: 1px solid #388bfd;
    padding: 5px 16px; font-weight: 700;
}
QPushButton#parseBtn:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                      stop:0 #58a6ff, stop:1 #388bfd);
    border-color: #58a6ff;
}
QPushButton#parseBtn:pressed { background-color: #1a5fd0; }
QPushButton#parseBtn:disabled { background-color: #161b22; color: #484f58; border-color: #21262d; }

/* ── Check box ── */
QCheckBox { color: #e6edf3; font-size: 12px; spacing: 6px; }
QCheckBox:disabled { color: #484f58; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #484f58; border-radius: 4px;
    background-color: #0d1117;
}
QCheckBox::indicator:hover { border-color: #58a6ff; background-color: #161b22; }
QCheckBox::indicator:checked { background-color: #1f6feb; border-color: #388bfd; image: url(@check@); }
QCheckBox::indicator:checked:hover { background-color: #388bfd; border-color: #58a6ff; }
QCheckBox::indicator:disabled { border-color: #30363d; background-color: #161b22; }

/* ── Tree view ── */
QTreeView {
    background-color: #0d1117; color: #e6edf3;
    border: 1px solid #21262d; border-radius: 6px;
    font-size: 12px; alternate-background-color: #10151c;
    outline: none; padding: 4px;
    show-decoration-selected: 1;
}
QTreeView::item { padding: 4px 4px; border-radius: 4px; }
QTreeView::item:hover { background-color: #161b22; }
QTreeView::item:selected { background-color: rgba(31, 111, 235, 0.55); color: #ffffff; }
QTreeView::item:selected:hover { background-color: rgba(31, 111, 235, 0.7); }
QTreeView::branch:has-children:!has-siblings:closed,
QTreeView::branch:closed:has-children:has-siblings {
    border-image: none; image: url(@chevron_right@);
}
QTreeView::branch:open:has-children:!has-siblings,
QTreeView::branch:open:has-children:has-siblings {
    border-image: none; image: url(@chevron_down@);
}
QTreeView::indicator {
    width: 14px; height: 14px;
    border: 1px solid #484f58; border-radius: 4px;
    background-color: #0d1117;
}
QTreeView::indicator:hover { border-color: #58a6ff; background-color: #161b22; }
QTreeView::indicator:checked { background-color: #1f6feb; border-color: #388bfd; image: url(@check@); }
QTreeView::indicator:checked:hover { background-color: #388bfd; border-color: #58a6ff; }
QTreeView::indicator:indeterminate { background-color: #1f6feb; border-color: #388bfd; image: url(@dash@); }
QTreeView::indicator:indeterminate:hover { background-color: #388bfd; border-color: #58a6ff; }

/* ── Headers ── */
QHeaderView { background-color: transparent; border: none; }
QHeaderView::section {
    background-color: #161b22; color: #8b949e;
    border: none; border-bottom: 1px solid #21262d; border-right: 1px solid #21262d;
    padding: 6px 8px; font-size: 11px; font-weight: 600;
}
QHeaderView::section:last, QHeaderView::section:only-one { border-right: none; }
QHeaderView::section:hover { color: #e6edf3; background-color: #1c2128; }
QTableCornerButton::section {
    background-color: #161b22; border: none;
    border-bottom: 1px solid #21262d; border-right: 1px solid #21262d;
}

/* ── Table widget ── */
QTableWidget {
    background-color: #0d1117; color: #e6edf3;
    border: 1px solid #21262d; border-radius: 6px;
    gridline-color: #161b22; font-size: 12px;
    alternate-background-color: #10151c; outline: none;
    selection-background-color: rgba(31, 111, 235, 0.55); selection-color: #ffffff;
}
QTableWidget::item { padding: 3px 8px; border: none; }
QTableWidget::item:hover { background-color: #161b22; }
QTableWidget::item:selected { background-color: rgba(31, 111, 235, 0.55); color: #ffffff; }

/* ── Tab widget (underline tabs) ── */
QTabWidget::pane {
    background-color: #0d1117; border: 1px solid #21262d;
    border-radius: 6px; top: -1px;
}
QTabWidget::tab-bar { left: 6px; }
QTabBar { background-color: transparent; }
QTabBar::tab {
    background-color: transparent; color: #8b949e;
    border: none; border-bottom: 2px solid transparent;
    padding: 7px 14px 8px 14px; margin-right: 6px;
    font-size: 12px; font-weight: 600; min-width: 80px;
}
QTabBar::tab:hover:!selected { color: #e6edf3; }
QTabBar::tab:selected { color: #e6edf3; border-bottom: 2px solid #58a6ff; }

/* ── Splitter ── */
QSplitter::handle { background-color: transparent; }
QSplitter::handle:horizontal { width: 6px; }
QSplitter::handle:vertical { height: 6px; }
QSplitter::handle:hover { background-color: #1f6feb; border-radius: 3px; }

/* ── Status bar ── */
QStatusBar {
    background-color: #161b22; color: #8b949e;
    border-top: 1px solid #21262d; font-size: 11px;
}
QStatusBar::item { border: none; }
QStatusBar QLabel { color: #8b949e; font-size: 11px; padding: 0px 6px; }

/* ── Scroll bars ── */
QScrollBar:vertical { background-color: transparent; width: 10px; margin: 2px; border: none; }
QScrollBar::handle:vertical { background-color: #30363d; border-radius: 3px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background-color: #484f58; }
QScrollBar::handle:vertical:pressed { background-color: #6e7681; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; background: none; border: none; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

QScrollBar:horizontal { background-color: transparent; height: 10px; margin: 2px; border: none; }
QScrollBar::handle:horizontal { background-color: #30363d; border-radius: 3px; min-width: 32px; }
QScrollBar::handle:horizontal:hover { background-color: #484f58; }
QScrollBar::handle:horizontal:pressed { background-color: #6e7681; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; background: none; border: none; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }
QAbstractScrollArea::corner { background-color: transparent; }

/* ── Spin box ── */
QSpinBox {
    background-color: #0d1117; color: #e6edf3;
    border: 1px solid #30363d; border-radius: 6px;
    padding: 2px 2px 2px 6px; font-size: 12px;
    selection-background-color: #1f6feb; selection-color: #ffffff;
}
QSpinBox:hover { border-color: #484f58; }
QSpinBox:focus { border-color: #58a6ff; }
QSpinBox:disabled { background-color: #161b22; color: #484f58; border-color: #21262d; }
QSpinBox::up-button, QSpinBox::down-button {
    subcontrol-origin: border; width: 16px;
    background-color: #161b22; border: none; border-left: 1px solid #30363d;
}
QSpinBox::up-button { subcontrol-position: top right; border-top-right-radius: 5px; }
QSpinBox::down-button { subcontrol-position: bottom right; border-bottom-right-radius: 5px; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background-color: #21262d; }
QSpinBox::up-button:pressed, QSpinBox::down-button:pressed { background-color: #30363d; }
QSpinBox::up-button:disabled, QSpinBox::down-button:disabled { border-left-color: #21262d; }
QSpinBox::up-arrow { image: url(@chevron_up_s@); width: 8px; height: 5px; }
QSpinBox::down-arrow { image: url(@chevron_down_s@); width: 8px; height: 5px; }
QSpinBox::up-arrow:disabled, QSpinBox::up-arrow:off { image: url(@chevron_up_s_dim@); }
QSpinBox::down-arrow:disabled, QSpinBox::down-arrow:off { image: url(@chevron_down_s_dim@); }

/* ── Menu ── */
QMenu {
    background-color: #161b22; color: #e6edf3;
    border: 1px solid #30363d; border-radius: 6px;
    padding: 6px;
}
QMenu::item { padding: 6px 28px 6px 12px; border-radius: 4px; font-size: 12px; }
QMenu::item:selected { background-color: #1f6feb; color: #ffffff; }
QMenu::item:disabled { color: #484f58; }
QMenu::separator { height: 1px; background-color: #21262d; margin: 6px 8px; }

/* ── Tooltip ── */
QToolTip {
    background-color: #161b22; color: #e6edf3;
    border: 1px solid #30363d; border-radius: 4px;
    padding: 5px 8px; font-size: 11px;
}

/* ── Message box ── */
QMessageBox { background-color: #161b22; }
QMessageBox QLabel { color: #e6edf3; font-size: 12px; }

/* ── Progress bar ── */
QProgressBar {
    background-color: #0d1117; border: 1px solid #30363d;
    border-radius: 4px; text-align: center; color: #8b949e;
    font-size: 11px; min-height: 18px;
}
QProgressBar::chunk { background-color: #1f6feb; border-radius: 3px; }
"""


_ui_icons_cache = None


def _build_ui_icons():
    """Paint the small glyphs the UI needs (chevrons, check marks, window
    control symbols) to PNG files and return {name: path}. QSS cannot draw
    shapes itself, the CSS border-triangle trick renders as a solid bar
    under Fusion, and Unicode symbols depend on font fallback — so they are
    rendered once per run (1x and @2x for high-DPI screens)."""
    global _ui_icons_cache
    if _ui_icons_cache is not None:
        return _ui_icons_cache
    out_dir = os.path.join(tempfile.gettempdir(), "can_parser_ui")
    os.makedirs(out_dir, exist_ok=True)
    # name: (width, height, pen width, [polyline, ...])
    chevrons = {
        "chevron_down": (10, 6, 1.5, [[(1.5, 1.5), (5, 4.5), (8.5, 1.5)]]),
        "chevron_up": (10, 6, 1.5, [[(1.5, 4.5), (5, 1.5), (8.5, 4.5)]]),
        "chevron_right": (6, 10, 1.5, [[(1.5, 1.5), (4.5, 5), (1.5, 8.5)]]),
        "chevron_down_s": (8, 5, 1.4, [[(1.2, 1.2), (4, 3.8), (6.8, 1.2)]]),
        "chevron_up_s": (8, 5, 1.4, [[(1.2, 3.8), (4, 1.2), (6.8, 3.8)]]),
    }
    marks = {
        "check": (14, 14, 2.0, [[(3, 7.2), (6, 10.2), (11, 4.4)]]),
        "dash": (14, 14, 2.0, [[(3.5, 7), (10.5, 7)]]),
    }
    window_controls = {
        "win_min": (10, 10, 1.2, [[(1.5, 5.5), (8.5, 5.5)]]),
        "win_max": (
            10,
            10,
            1.2,
            [[(1.5, 1.5), (8.5, 1.5), (8.5, 8.5), (1.5, 8.5), (1.5, 1.5)]],
        ),
        "win_restore": (
            10,
            10,
            1.2,
            [
                [(1.5, 3.5), (6.5, 3.5), (6.5, 8.5), (1.5, 8.5), (1.5, 3.5)],
                [(3.5, 3.5), (3.5, 1.5), (8.5, 1.5), (8.5, 6.5), (6.5, 6.5)],
            ],
        ),
        "win_close": (
            10,
            10,
            1.2,
            [[(1.5, 1.5), (8.5, 8.5)], [(8.5, 1.5), (1.5, 8.5)]],
        ),
    }
    paths = {}

    def render(name, w, h, pen_w, polylines, color):
        for scale, suffix in ((1, ""), (2, "@2x")):
            pix = QPixmap(w * scale, h * scale)
            pix.fill(Qt.transparent)
            p = QPainter(pix)
            p.setRenderHint(QPainter.Antialiasing)
            p.scale(scale, scale)
            p.setPen(
                QPen(QColor(color), pen_w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            )
            for pts in polylines:
                p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in pts]))
            p.end()
            pix.save(os.path.join(out_dir, f"{name}{suffix}.png"), "PNG")
        paths[name] = os.path.join(out_dir, f"{name}.png").replace("\\", "/")

    for name, (w, h, pen_w, polys) in chevrons.items():
        render(name, w, h, pen_w, polys, "#8b949e")
        render(name + "_dim", w, h, pen_w, polys, "#484f58")
    for name, (w, h, pen_w, polys) in marks.items():
        render(name, w, h, pen_w, polys, "#ffffff")
    for name, (w, h, pen_w, polys) in window_controls.items():
        render(name, w, h, pen_w, polys, "#c9d1d9")
    _ui_icons_cache = paths
    return paths


def _glyph_icon(name):
    """QIcon for a runtime-rendered glyph, with its @2x variant attached so
    it stays crisp on high-DPI screens."""
    path = _build_ui_icons()[name]
    icon = QIcon(path)
    hi_res = path[:-4] + "@2x.png"
    if os.path.exists(hi_res):
        pix = QPixmap(hi_res)
        pix.setDevicePixelRatio(2.0)
        icon.addPixmap(pix)
    return icon


def build_stylesheet():
    sheet = STYLESHEET
    for name, path in _build_ui_icons().items():
        sheet = sheet.replace(f"@{name}@", path)
    return sheet


class _TitleBar(QWidget):
    """Custom frameless title bar with window control buttons."""

    def __init__(self, parent, icon_path=None):
        super().__init__(parent)
        self._parent = parent
        self._drag_pos = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(0)

        icon_label = QLabel()
        if icon_path:
            pix = QPixmap(icon_path).scaled(
                20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            icon_label.setPixmap(pix)
            icon_label.setFixedSize(28, 36)
            icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        self._icon = QLabel("CAN Bus Parser")
        self._icon.setObjectName("titleLabel")
        self._icon.setMinimumHeight(36)
        layout.addWidget(self._icon, 1)

        btn_min = QPushButton()
        btn_min.setObjectName("titleBtn")
        btn_min.setIcon(_glyph_icon("win_min"))
        btn_min.setIconSize(QSize(10, 10))
        btn_min.clicked.connect(parent.showMinimized)
        btn_min.setFixedSize(44, 36)
        layout.addWidget(btn_min)

        self._btn_max = QPushButton()
        self._btn_max.setObjectName("titleBtn")
        self._btn_max.setIcon(_glyph_icon("win_max"))
        self._btn_max.setIconSize(QSize(10, 10))
        self._btn_max.clicked.connect(self._toggle_max)
        self._btn_max.setFixedSize(44, 36)
        layout.addWidget(self._btn_max)

        btn_close = QPushButton()
        btn_close.setObjectName("titleClose")
        btn_close.setIcon(_glyph_icon("win_close"))
        btn_close.setIconSize(QSize(10, 10))
        btn_close.clicked.connect(parent.close)
        btn_close.setFixedSize(44, 36)
        layout.addWidget(btn_close)

    def _toggle_max(self):
        if self._parent.isMaximized():
            self._parent.showNormal()
            self._btn_max.setIcon(_glyph_icon("win_max"))
        else:
            self._parent.showMaximized()
            self._btn_max.setIcon(_glyph_icon("win_restore"))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            delta = event.globalPos() - self._drag_pos
            self._parent.move(self._parent.pos() + delta)
            self._drag_pos = event.globalPos()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._toggle_max()
        super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint)
        self.setWindowTitle("CAN Bus Parser")
        self.resize(1400, 900)
        self.setMinimumSize(900, 600)

        self._dbc_loader = DbcLoader()
        self._backend = CanBackend()
        self._live_view = LiveView(self._backend, self._dbc_loader)
        self._log_view = LogView()

        self._icon_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "can-bus.png",
        )
        self._msg_count = 0
        self._init_ui()
        self._connect_all()

    def _init_ui(self):
        wrapper = QWidget()
        wrapper.setObjectName("mainWrapper")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)

        self._title_bar = _TitleBar(self, self._icon_path)
        wl.addWidget(self._title_bar)

        self._create_toolbar()
        wl.addWidget(self._toolbar)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(8, 8, 8, 8)
        self._create_central_layout(cl)
        wl.addWidget(content, 1)

        self._create_statusbar()
        wl.addWidget(self._status)

        self.setCentralWidget(wrapper)

    def _create_toolbar(self):
        self._toolbar = tb = QToolBar("Main")
        tb.setMovable(False)

        tb.addWidget(QLabel(" DBC: "))
        self._dbc_path = QLineEdit()
        self._dbc_path.setReadOnly(True)
        self._dbc_path.setFixedWidth(200)
        self._dbc_path.setPlaceholderText("Select .dbc file...")
        tb.addWidget(self._dbc_path)

        self._dbc_btn = QPushButton("...")
        self._dbc_btn.clicked.connect(self._select_dbc)
        tb.addWidget(self._dbc_btn)

        tb.addSeparator()

        tb.addWidget(QLabel(" Channel: "))
        self._channel_combo = QComboBox()
        self._channel_combo.addItems(
            [
                "PCAN_USBBUS1",
                "PCAN_USBBUS2",
                "PCAN_USBBUS3",
                "PCAN_USBBUS4",
                "PCAN_USBBUS5",
                "PCAN_USBBUS6",
                "PCAN_USBBUS7",
                "PCAN_USBBUS8",
            ]
        )
        tb.addWidget(self._channel_combo)

        tb.addWidget(QLabel(" Bitrate: "))
        self._bitrate_combo = QComboBox()
        self._bitrate_combo.addItems(["125000", "250000", "500000", "1000000"])
        self._bitrate_combo.setCurrentText("500000")
        tb.addWidget(self._bitrate_combo)

        tb.addSeparator()

        self._start_btn = QPushButton("Start")
        self._start_btn.setObjectName("startBtn")
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("stopBtn")
        self._stop_btn.setEnabled(False)
        tb.addWidget(self._start_btn)
        tb.addWidget(self._stop_btn)

    def _create_central_layout(self, layout):
        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)

        tree_header = QHBoxLayout()
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search signals...")
        tree_header.addWidget(self._search_edit)
        ll.addLayout(tree_header)

        btn_layout = QHBoxLayout()
        self._select_all_btn = QPushButton("Select All")
        self._select_all_btn.setFixedHeight(24)
        self._deselect_all_btn = QPushButton("Deselect All")
        self._deselect_all_btn.setFixedHeight(24)
        btn_layout.addWidget(self._select_all_btn)
        btn_layout.addWidget(self._deselect_all_btn)
        ll.addLayout(btn_layout)

        self._tree_view = QTreeView()
        self._tree_view.setModel(self._dbc_loader.model)
        self._tree_view.setAlternatingRowColors(True)
        self._tree_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree_view.customContextMenuRequested.connect(self._on_tree_context_menu)
        # Clicking a signal row (not the checkbox) highlights its plot line.
        self._tree_view.clicked.connect(self._on_tree_clicked)
        self._tree_view.expandAll()
        ll.addWidget(self._tree_view)

        splitter.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)
        rl.addWidget(self._live_view, 1)
        rl.addWidget(self._log_view)

        splitter.addWidget(right)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setSizes([280, 1100])

        layout.addWidget(splitter)

    def _create_statusbar(self):
        self._status = QStatusBar()
        self._status_label = QLabel("Ready")
        self._msg_label = QLabel("Messages: 0")
        self._status.addWidget(self._status_label, 1)
        self._status.addPermanentWidget(self._msg_label)
        # Frames arrive at 500-1000 fps — relayouting the label per frame
        # dominated the per-frame UI cost. Update it on a timer instead.
        self._msg_count = 0
        self._msg_timer = QTimer(self)
        self._msg_timer.timeout.connect(self._flush_msg_count)
        self._msg_timer.start(250)

    def _flush_msg_count(self):
        self._msg_label.setText(f"Messages: {self._msg_count}")

    def _connect_all(self):
        self._start_btn.clicked.connect(self._start)
        self._stop_btn.clicked.connect(self._stop)

        self._dbc_loader.dbc_loaded.connect(self._on_dbc_loaded)
        self._dbc_loader.error_occurred.connect(self._show_error)

        self._backend.message_received.connect(self._on_message)
        self._backend.error_occurred.connect(self._on_backend_error)
        self._backend.stopped.connect(self._on_stopped)
        self._backend.parse_progress.connect(self._on_parse_progress)
        self._backend.parsed_ready.connect(self._on_parsed_ready)

        self._live_view.cleared.connect(self._on_cleared)
        self._live_view.signal_label_clicked.connect(self._on_plot_label_clicked)
        self._live_view.status_message.connect(lambda m: self._status_label.setText(m))

        self._dbc_loader.model.itemChanged.connect(self._on_tree_check_changed)

        self._search_edit.textChanged.connect(self._on_search)
        self._select_all_btn.clicked.connect(self._on_select_all)
        self._deselect_all_btn.clicked.connect(self._on_deselect_all)

        self._log_view.file_selected.connect(self._on_log_file)
        self._log_view.play_requested.connect(self._play_log)
        self._log_view.stop_requested.connect(self._stop_playback)

    def _select_dbc(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select DBC File", "", "DBC Files (*.dbc);;All (*)"
        )
        if f:
            self._dbc_path.setText(f)
            self._dbc_loader.load(f)

    def _on_dbc_loaded(self, db):
        self._backend.set_dbc(db)
        self._tree_view.expandAll()
        self._sync_checked_signals()
        self._status_label.setText(f"DBC loaded: {len(db.messages)} messages")
        self._on_search(self._search_edit.text())

    def _sync_checked_signals(self):
        checked = self._dbc_loader.get_checked_signals()
        self._backend.set_checked_signals(checked)
        self._live_view.refresh_signals(checked)

    def _on_tree_check_changed(self, item):
        self._dbc_loader.cascade_check_state(item)
        # debounce: batch rapid checkbox changes into a single sync
        if not hasattr(self, "_sync_timer"):
            self._sync_timer = QTimer(self)
            self._sync_timer.setSingleShot(True)
            self._sync_timer.timeout.connect(self._sync_checked_signals)
        self._sync_timer.stop()
        self._sync_timer.start(80)

    def _on_search(self, text):
        text = text.strip().lower()
        model = self._dbc_loader.model
        ITEM_TYPE_MUX_GROUP = self._dbc_loader.ITEM_TYPE_MUX_GROUP

        if not text:
            # Unhide everything (including mux-group sub-rows)
            for row in range(model.rowCount()):
                msg_item = model.item(row)
                self._tree_view.setRowHidden(
                    row, model.invisibleRootItem().index(), False
                )
                for cr in range(msg_item.rowCount()):
                    child = msg_item.child(cr)
                    self._tree_view.setRowHidden(cr, msg_item.index(), False)
                    if child.data(self._dbc_loader.CHECKED_ROLE) == ITEM_TYPE_MUX_GROUP:
                        for sr in range(child.rowCount()):
                            self._tree_view.setRowHidden(sr, child.index(), False)
            return

        self._tree_view.expandAll()
        for row in range(model.rowCount()):
            msg_item = model.item(row)
            can_id = msg_item.data(self._dbc_loader.CAN_ID_ROLE)
            msg_match = (
                text in msg_item.text().lower() or text in f"0x{can_id:03x}".lower()
            )
            any_child_match = False
            for cr in range(msg_item.rowCount()):
                child = msg_item.child(cr)
                child_type = child.data(self._dbc_loader.CHECKED_ROLE)

                if child_type == ITEM_TYPE_MUX_GROUP:
                    # Search inside the mux group
                    group_match = False
                    for sr in range(child.rowCount()):
                        sig_item = child.child(sr)
                        sig_match = text in sig_item.text().lower()
                        self._tree_view.setRowHidden(
                            sr, child.index(), not sig_match and not msg_match
                        )
                        group_match = group_match or sig_match
                    # Show/hide the mux group itself
                    self._tree_view.setRowHidden(
                        cr, msg_item.index(), not group_match and not msg_match
                    )
                    any_child_match = any_child_match or group_match
                else:
                    # Direct signal child (plain signal or [MUX] signal)
                    sig_match = text in child.text().lower()
                    self._tree_view.setRowHidden(
                        cr, msg_item.index(), not sig_match and not msg_match
                    )
                    any_child_match = any_child_match or sig_match

            self._tree_view.setRowHidden(
                row,
                model.invisibleRootItem().index(),
                not msg_match and not any_child_match,
            )

    def _on_select_all(self):
        self._dbc_loader.select_all()
        self._sync_checked_signals()

    def _on_deselect_all(self):
        self._dbc_loader.deselect_all()
        self._sync_checked_signals()

    def _on_tree_context_menu(self, pos):
        idx = self._tree_view.indexAt(pos)
        if not idx.isValid():
            return
        item = self._dbc_loader.model.itemFromIndex(idx)
        item_type = item.data(self._dbc_loader.CHECKED_ROLE)
        if item_type != self._dbc_loader.ITEM_TYPE_SIGNAL:
            return
        can_id = item.data(self._dbc_loader.CAN_ID_ROLE)
        sig_obj = item.data(self._dbc_loader.SIGNAL_OBJ_ROLE)
        # Use the real signal name, not the display label (which may include
        # " [MUX]" suffix for multiplexor signals).
        sig_name = sig_obj.name if sig_obj is not None else item.text()
        menu = QMenu(self)
        action = menu.addAction(f'Add copy of "{sig_name}" to plot')
        action.triggered.connect(
            lambda: self._live_view.add_signal_instance(can_id, sig_name)
        )
        menu.exec_(self._tree_view.viewport().mapToGlobal(pos))

    def _on_plot_label_clicked(self, can_id, sig_name):
        """A legend label or plot line was clicked in the Signal Plot — check
        that signal in the tree (and scroll to it) so all three areas stay
        in sync: legend highlight ↔ plot line highlight ↔ tree selection."""
        item = self._dbc_loader._signal_items.get((can_id, sig_name))
        if item is None:
            return
        if item.checkState() != Qt.Checked:
            item.setCheckState(Qt.Checked)  # triggers _on_tree_check_changed → sync
        # Reveal the item in the tree.
        idx = item.index()
        self._tree_view.scrollTo(idx)
        self._tree_view.setCurrentIndex(idx)

    def _on_tree_clicked(self, index):
        """A tree row was clicked — if it is a signal, highlight its plot line
        and legend so the tree selection, plot line and legend stay in sync."""
        item = self._dbc_loader.model.itemFromIndex(index)
        item_type = item.data(self._dbc_loader.CHECKED_ROLE)
        if item_type != self._dbc_loader.ITEM_TYPE_SIGNAL:
            self._live_view._plot.clear_highlight()
            return
        can_id = item.data(self._dbc_loader.CAN_ID_ROLE)
        sig_obj = item.data(self._dbc_loader.SIGNAL_OBJ_ROLE)
        sig_name = sig_obj.name if sig_obj is not None else item.text()
        self._live_view._plot.highlight_signal(can_id, sig_name)

    def _start(self):
        channel = self._channel_combo.currentText()
        bitrate = int(self._bitrate_combo.currentText())
        if not self._backend.start_live(channel=channel, bitrate=bitrate):
            return  # error already surfaced; keep the buttons usable
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._status_label.setText(
            f"Live: {channel} @ {bitrate // 1000}k  —  "
            "Save CSV exports raw CAN Log (ASC)"
        )

    def _stop(self):
        """Toolbar Stop — stops live capture or log playback."""
        mode = self._backend.mode()
        if mode == "playback":
            self._stop_playback()
        elif mode == "live":
            self._backend.stop()
            self._live_view.flush_buffer()
            self._start_btn.setEnabled(True)
            self._stop_btn.setEnabled(False)
            self._status_label.setText("Stopped")

    def _stop_playback(self):
        """LogView Stop — stops local log parsing/replay only."""
        self._backend.stop()
        self._live_view.flush_buffer()
        self._log_view.set_playing(False)
        self._status_label.setText("Playback stopped")

    def _on_stopped(self):
        """Backend finished on its own (e.g. replay reached end of log)."""
        mode = self._backend.mode()
        self._live_view.flush_buffer()
        if mode == "live":
            self._start_btn.setEnabled(True)
            self._stop_btn.setEnabled(False)
        else:
            self._log_view.set_playing(False)

    def _on_cleared(self):
        self._msg_count = 0
        self._msg_label.setText("Messages: 0")

    def _on_message(self, msg, decoded):
        # Playback rows were already counted when the parse finished —
        # counting them again would double the label.
        if self._backend.mode() == "playback":
            return
        self._msg_count += 1

    def _on_parse_progress(self, done, total):
        if total > 0:
            self._status_label.setText(
                f"Parsing log... {done}/{total} ({done * 100 // total}%)"
            )
        else:
            # Streamed sources don't know the total up front — show the count.
            self._status_label.setText(f"Parsing log... {done} frames")

    def _on_parsed_ready(self):
        # Bulk-load all checked signals from the pre-decoded index so the plot
        # and table reflect the whole file instantly; the replay thread then
        # only animates the timeline.
        self._live_view.load_parsed_series()
        self._msg_count = len(self._backend.parsed_messages())
        self._msg_label.setText(f"Messages: {self._msg_count}")
        self._status_label.setText(
            "Playing log file  —  Save CSV exports parsed signal data"
        )

    def _on_log_file(self, filepath):
        self._status_label.setText(f"Log file: {filepath}")

    def _play_log(self):
        filepath = self._log_view._filepath
        if not filepath:
            self._status_label.setText("No log file selected")
            return
        # flush any pending debounce so signal cache is current
        if hasattr(self, "_sync_timer") and self._sync_timer.isActive():
            self._sync_timer.stop()
        self._live_view._clear()
        self._sync_checked_signals()
        self._msg_count = 0
        self._msg_label.setText("Messages: 0")
        # Two-stage: parse the whole file first (status updated via
        # parse_progress / parsed_ready), then replay by timestamp.
        self._backend.start_playback(filepath)
        # Only the LogView Play/Stop controls reflect playback state —
        # the toolbar Start/Stop belong to PCAN live capture and stay
        # independent so the user can run a live capture alongside.
        self._log_view.set_playing(True)
        self._status_label.setText("Parsing log file...")

    def _on_backend_error(self, msg):
        self._status_label.setText(f"Error: {msg}")
        # A failed parse leaves the LogView in "playing" state (Play disabled,
        # Stop enabled) — restore the buttons so the user can retry.
        self._log_view.set_playing(False)

    def _show_error(self, msg):
        QMessageBox.critical(self, "Error", msg)

    def closeEvent(self, event):
        """Stop all background threads before the window is destroyed.

        Without this, Qt prints "QThread: Destroyed while thread is still
        running" (and may crash) when the user closes the app mid-parse or
        mid-replay.
        """
        try:
            self._live_view.flush_buffer()
        except Exception:
            pass
        try:
            self._backend.stop()
        except Exception:
            pass
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setAttribute(Qt.AA_UseHighDpiPixmaps)

    # Dark palette as base (for any widgets not covered by QSS)
    from PyQt5.QtGui import QPalette

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#0f1117"))
    palette.setColor(QPalette.WindowText, QColor("#e6edf3"))
    palette.setColor(QPalette.Base, QColor("#0d1117"))
    palette.setColor(QPalette.AlternateBase, QColor("#161b22"))
    palette.setColor(QPalette.ToolTipBase, QColor("#161b22"))
    palette.setColor(QPalette.ToolTipText, QColor("#e6edf3"))
    palette.setColor(QPalette.Text, QColor("#e6edf3"))
    palette.setColor(QPalette.Button, QColor("#21262d"))
    palette.setColor(QPalette.ButtonText, QColor("#e6edf3"))
    palette.setColor(QPalette.BrightText, QColor("#58a6ff"))
    palette.setColor(QPalette.Link, QColor("#58a6ff"))
    palette.setColor(QPalette.Highlight, QColor("#1f6feb"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#484f58"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#484f58"))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#484f58"))
    app.setPalette(palette)

    # Segoe UI at 9pt (12px) is the Windows UI standard and matches the
    # pixel sizes used throughout the stylesheet; YaHei covers CJK text.
    font = app.font()
    if hasattr(font, "setFamilies"):
        font.setFamilies(["Segoe UI", "Microsoft YaHei UI", "Arial"])
    else:
        font.setFamily("Segoe UI")
    font.setPointSize(9)
    app.setFont(font)

    app.setStyleSheet(build_stylesheet())
    icon_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(icon_dir, "can-bus.png")
    app_icon = QIcon(icon_path)
    app.setWindowIcon(app_icon)
    window = MainWindow()
    window.setWindowIcon(app_icon)

    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
