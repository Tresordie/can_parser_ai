"""Log file selection and playback control panel."""

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLineEdit, QFileDialog,
)


class LogView(QWidget):
    file_selected = pyqtSignal(str)
    play_requested = pyqtSignal()
    stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filepath = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)

        self._browse_btn = QPushButton("Log File...")
        self._browse_btn.setFixedHeight(28)
        self._browse_btn.clicked.connect(self._browse)
        layout.addWidget(self._browse_btn)

        self._path_edit = QLineEdit()
        self._path_edit.setReadOnly(True)
        self._path_edit.setPlaceholderText("Select CAN log file (.asc, .csv, .blf)...")
        layout.addWidget(self._path_edit, 1)

        self._play_btn = QPushButton("Play")
        self._play_btn.setFixedHeight(28)
        self._play_btn.setEnabled(False)
        self._play_btn.clicked.connect(self.play_requested.emit)
        layout.addWidget(self._play_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setFixedHeight(28)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        layout.addWidget(self._stop_btn)

    def _browse(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "Select CAN Log File", "",
            "CAN Log Files (*.asc *.csv *.blf *.trc);;All (*)"
        )
        if f:
            self._filepath = f
            self._path_edit.setText(f)
            self._play_btn.setEnabled(True)
            self.file_selected.emit(f)

    def set_playing(self, playing):
        self._play_btn.setEnabled(not playing)
        self._stop_btn.setEnabled(playing)
        self._browse_btn.setEnabled(not playing)
