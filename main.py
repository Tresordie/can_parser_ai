"""CAN Bus Parser GUI — main entry point."""

import os
import sys

from can_backend import CanBackend
from dbc_loader import DbcLoader
from live_view import LiveView
from log_view import LogView
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
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
from workers import CanWorker

STYLESHEET = """
QMainWindow { background-color: #f0f2f5; }
QToolBar {
    background-color: #ffffff; border-bottom: 1px solid #e9ecef;
    padding: 4px 6px; spacing: 4px;
}
QToolBar QLabel { color: #495057; font-size: 12px; font-weight: 600; }
QLineEdit {
    background-color: #ffffff; color: #212529;
    border: 1px solid #dee2e6; border-radius: 5px;
    padding: 4px 8px; font-size: 12px;
}
QLineEdit:focus { border-color: #4263eb; }
QComboBox {
    background-color: #ffffff; color: #212529;
    border: 1px solid #dee2e6; border-radius: 5px;
    padding: 3px 8px; font-size: 12px; min-width: 100px;
}
QComboBox:hover { border-color: #adb5bd; }
QComboBox:focus { border-color: #4263eb; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background-color: #ffffff; color: #212529;
    selection-background-color: #4263eb; selection-color: #ffffff;
    border: 1px solid #dee2e6; border-radius: 4px;
}
QPushButton {
    background-color: #e8edf5; color: #4263eb;
    border: 1px solid #d5ddf0; border-radius: 5px;
    padding: 5px 14px; font-size: 12px; font-weight: 600;
}
QPushButton:hover { background-color: #dbe4f2; }
QPushButton:pressed { background-color: #cdd8eb; }
QPushButton:disabled {
    background-color: #e9ecef; color: #adb5bd; border: none;
}
QPushButton#titleBtn {
    background-color: transparent; color: #868e96;
    border: none; border-radius: 0px;
    padding: 0px; font-size: 14px; font-weight: normal;
    min-width: 40px; min-height: 28px;
}
QPushButton#titleBtn:hover { background-color: #f1f3f5; color: #495057; }
QPushButton#titleClose { background-color: transparent; color: #868e96;
    border: none; border-radius: 0px; padding: 0px;
    font-size: 14px; min-width: 40px; min-height: 28px; }
QPushButton#titleClose:hover { background-color: #e03131; color: #ffffff; }
QTreeView {
    background-color: #ffffff; color: #212529;
    border: 1px solid #e9ecef; border-radius: 5px;
    font-size: 12px; alternate-background-color: #f8f9fa;
}
QTreeView::item:hover { background-color: #f1f3f5; }
QTreeView::item:selected { background-color: #4263eb; color: #ffffff; }
QTableWidget {
    background-color: #ffffff; color: #212529;
    border: 1px solid #e9ecef; border-radius: 5px;
    gridline-color: #f1f3f5; font-size: 11px;
    alternate-background-color: #f8f9fa;
}
QTableWidget::item:selected { background-color: #4263eb; color: #ffffff; }
QHeaderView::section {
    background-color: #f8f9fa; color: #495057;
    border: none; border-bottom: 1px solid #e9ecef;
    padding: 5px 8px; font-size: 11px; font-weight: 600;
}
QTabWidget::pane {
    background-color: #ffffff; border: 1px solid #e9ecef; border-radius: 5px;
}
QTabBar::tab {
    background-color: #f1f3f5; color: #868e96;
    border: 1px solid #e9ecef; border-bottom: none;
    border-top-left-radius: 5px; border-top-right-radius: 5px;
    padding: 6px 16px; font-size: 12px; margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #ffffff; color: #4263eb;
    border-bottom: 2px solid #4263eb;
}
QTabBar::tab:hover:!selected { color: #495057; background-color: #e9ecef; }
QSplitter::handle { background-color: #e9ecef; width: 2px; }
QStatusBar {
    background-color: #ffffff; color: #868e96;
    border-top: 1px solid #e9ecef; font-size: 11px; padding: 2px 8px;
}
QScrollBar:vertical {
    background-color: #f8f9fa; width: 8px; border: none;
}
QScrollBar::handle:vertical {
    background-color: #ced4da; border-radius: 4px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background-color: #adb5bd; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar:horizontal {
    background-color: #f8f9fa; height: 8px; border: none;
}
QScrollBar::handle:horizontal {
    background-color: #ced4da; border-radius: 4px; min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background-color: #adb5bd; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
"""

TITLE_BAR_STYLE = """
#titleBar {
    background-color: #ffffff; border-bottom: 1px solid #e9ecef;
}
#titleLabel {
    color: #212529; font-size: 12px; font-weight: 600;
    padding-left: 10px;
}
"""


class _TitleBar(QWidget):
    """Custom frameless title bar with window control buttons."""

    def __init__(self, parent, icon_path=None):
        super().__init__(parent)
        self._parent = parent
        self._drag_pos = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        icon_label = QLabel()
        if icon_path:
            pix = QPixmap(icon_path).scaled(
                20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            icon_label.setPixmap(pix)
            icon_label.setFixedSize(24, 32)
            icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        self._icon = QLabel("CAN Bus Parser")
        self._icon.setObjectName("titleLabel")
        self._icon.setMinimumHeight(32)
        layout.addWidget(self._icon, 1)

        btn_min = QPushButton("−")
        btn_min.setObjectName("titleBtn")
        btn_min.clicked.connect(parent.showMinimized)
        btn_min.setFixedSize(40, 32)
        layout.addWidget(btn_min)

        self._btn_max = QPushButton("□")
        self._btn_max.setObjectName("titleBtn")
        self._btn_max.clicked.connect(self._toggle_max)
        self._btn_max.setFixedSize(40, 32)
        layout.addWidget(self._btn_max)

        btn_close = QPushButton("✕")
        btn_close.setObjectName("titleClose")
        btn_close.clicked.connect(parent.close)
        btn_close.setFixedSize(40, 32)
        layout.addWidget(btn_close)

    def _toggle_max(self):
        if self._parent.isMaximized():
            self._parent.showNormal()
            self._btn_max.setText("□")
        else:
            self._parent.showMaximized()
            self._btn_max.setText("❐")

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
        self._worker = None
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
        cl.setContentsMargins(0, 0, 0, 0)
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
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setEnabled(False)
        tb.addWidget(self._start_btn)
        tb.addWidget(self._stop_btn)

    def _create_central_layout(self, layout):
        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

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
        self._tree_view.expandAll()
        ll.addWidget(self._tree_view)

        splitter.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self._live_view, 1)
        rl.addWidget(self._log_view)

        splitter.addWidget(right)
        splitter.setSizes([320, 1060])

        layout.addWidget(splitter)

    def _create_statusbar(self):
        self._status = QStatusBar()
        self._status_label = QLabel("Ready")
        self._msg_label = QLabel("Messages: 0")
        self._status.addWidget(self._status_label, 1)
        self._status.addPermanentWidget(self._msg_label)

    def _connect_all(self):
        self._start_btn.clicked.connect(self._start)
        self._stop_btn.clicked.connect(self._stop)

        self._dbc_loader.dbc_loaded.connect(self._on_dbc_loaded)
        self._dbc_loader.error_occurred.connect(self._show_error)

        self._backend.message_received.connect(self._on_message)
        self._backend.error_occurred.connect(
            lambda m: self._status_label.setText(f"Error: {m}")
        )
        self._backend.stopped.connect(self._on_stopped)

        self._live_view.cleared.connect(self._on_cleared)

        self._dbc_loader.model.itemChanged.connect(self._on_tree_check_changed)

        self._search_edit.textChanged.connect(self._on_search)
        self._select_all_btn.clicked.connect(self._on_select_all)
        self._deselect_all_btn.clicked.connect(self._on_deselect_all)

        self._log_view.file_selected.connect(self._on_log_file)
        self._log_view.play_requested.connect(self._play_log)
        self._log_view.stop_requested.connect(self._stop)

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
        self._sync_checked_signals()

    def _on_search(self, text):
        text = text.strip().lower()
        model = self._dbc_loader.model
        if not text:
            for row in range(model.rowCount()):
                msg_item = model.item(row)
                self._tree_view.setRowHidden(
                    row, model.invisibleRootItem().index(), False
                )
                for cr in range(msg_item.rowCount()):
                    self._tree_view.setRowHidden(cr, msg_item.index(), False)
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
                sig_item = msg_item.child(cr)
                sig_match = text in sig_item.text().lower()
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

    def _start(self):
        channel = self._channel_combo.currentText()
        bitrate = int(self._bitrate_combo.currentText())
        self._backend.start_live(channel=channel, bitrate=bitrate)
        self._worker = CanWorker(self._backend)
        self._worker.start()
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._status_label.setText(f"Connected: {channel} @ {bitrate // 1000}k")

    def _stop(self):
        self._backend.stop()
        if self._worker:
            self._worker.stop()
            self._worker = None
        self._live_view.flush_buffer()
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._log_view.set_playing(False)
        self._status_label.setText("Stopped")

    def _on_stopped(self):
        self._live_view.flush_buffer()
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._log_view.set_playing(False)

    def _on_cleared(self):
        self._msg_count = 0
        self._msg_label.setText("Messages: 0")

    def _on_message(self, msg, decoded):
        self._msg_count += 1
        self._msg_label.setText(f"Messages: {self._msg_count}")

    def _on_log_file(self, filepath):
        self._status_label.setText(f"Log file: {filepath}")

    def _play_log(self):
        filepath = self._log_view._filepath
        if not filepath:
            self._status_label.setText("No log file selected")
            return
        self._backend.start_playback(filepath)
        self._log_view.set_playing(True)
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._status_label.setText("Playing log file...")

    def _show_error(self, msg):
        QMessageBox.critical(self, "Error", msg)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = app.font()
    font.setFamily("FiraCode Nerd Font")
    font.setPointSize(10)
    font.setStyleHint(font.Monospace)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET + TITLE_BAR_STYLE)
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
