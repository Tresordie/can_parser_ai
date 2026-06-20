"""Live data display — text table and signal plot tabs."""

import csv
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QPushButton, QFileDialog, QHeaderView, QLabel,
    QSpinBox,
)
from signal_plot import SignalPlot


class LiveView(QWidget):
    cleared = pyqtSignal()
    MAX_TABLE_ROWS = 1000
    FLUSH_INTERVAL_MS = 100

    def __init__(self, backend, dbc_loader, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._dbc_loader = dbc_loader

        self._data_rows = []
        self._checked_signals = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()

        self._table = QTableWidget()
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabs.addTab(self._table, "Data Table")

        self._plot = SignalPlot()
        self._tabs.addTab(self._plot, "Signal Plot")

        layout.addWidget(self._tabs, 1)

        btn_layout = QHBoxLayout()
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedHeight(28)
        self._clear_btn.clicked.connect(self._clear)
        btn_layout.addWidget(self._clear_btn)

        self._save_btn = QPushButton("Save CSV")
        self._save_btn.setFixedHeight(28)
        self._save_btn.clicked.connect(self._save_csv)
        btn_layout.addWidget(self._save_btn)

        btn_layout.addStretch()

        btn_layout.addWidget(QLabel("Legend:"))
        self._legend_size = QSpinBox()
        self._legend_size.setRange(4, 20)
        self._legend_size.setValue(8)
        self._legend_size.setFixedWidth(48)
        self._legend_size.setFixedHeight(24)
        self._legend_size.valueChanged.connect(self._plot.set_legend_fontsize)
        btn_layout.addWidget(self._legend_size)

        layout.addLayout(btn_layout)

        backend.message_received.connect(self._on_message)

        self._msg_buffer = []
        self._flush_timer = QTimer(self)
        self._flush_timer.timeout.connect(self._flush_buffer)
        self._flush_timer.start(self.FLUSH_INTERVAL_MS)

        self._plot_timer = QTimer(self)
        self._plot_timer.timeout.connect(self._plot.update_plot)
        self._plot_timer.start(1000)

    def refresh_signals(self, checked_signals):
        old_names = {sig_name for _, sig_name, _ in self._checked_signals}
        new_names = {sig_name for _, sig_name, _ in checked_signals}
        added = new_names - old_names

        self._checked_signals = checked_signals
        self._plot.set_signals(checked_signals)

        headers = ["Timestamp"]
        for can_id, sig_name, _sig in checked_signals:
            headers.append(f"0x{can_id:03X}/{sig_name}")
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)

        if added:
            added_can_map = {}
            for can_id, sig_name, sig_obj in checked_signals:
                if sig_name in added:
                    added_can_map[sig_name] = can_id
            for ts, decoded in self._backend.parsed_messages():
                if decoded is None:
                    continue
                for sig_name in added:
                    val = decoded.get(sig_name)
                    if val is not None:
                        can_id = added_can_map[sig_name]
                        self._plot.add_point(ts, can_id, sig_name, val)

        self._rebuild_table()

    def _rebuild_table(self):
        self._table.setRowCount(0)
        for row in self._data_rows:
            row_idx = self._table.rowCount()
            self._table.insertRow(row_idx)
            self._table.setItem(row_idx, 0, QTableWidgetItem(f"{row['ts']:.6f}"))
            for col, (can_id, sig_name, _sig) in enumerate(self._checked_signals, 1):
                val = row["decoded"].get(sig_name)
                if val is not None:
                    self._table.setItem(row_idx, col, QTableWidgetItem(str(val)))

    def _on_message(self, msg, decoded):
        if not self._checked_signals or decoded is None:
            return
        self._msg_buffer.append((msg, decoded))

    def _flush_buffer(self):
        if not self._msg_buffer:
            return

        batch = self._msg_buffer
        self._msg_buffer = []

        table = self._table
        data_rows = self._data_rows
        checked = self._checked_signals
        plot = self._plot
        max_rows = self.MAX_TABLE_ROWS

        table.setUpdatesEnabled(False)
        for msg, decoded in batch:
            ts = msg.timestamp
            row_idx = table.rowCount()
            table.insertRow(row_idx)
            table.setItem(row_idx, 0, QTableWidgetItem(f"{ts:.6f}"))
            has_value = False

            for col, (can_id, sig_name, _sig) in enumerate(checked, 1):
                val = decoded.get(sig_name)
                if val is not None:
                    table.setItem(row_idx, col, QTableWidgetItem(str(val)))
                    plot.add_point(ts, can_id, sig_name, val)
                    has_value = True

            if not has_value:
                table.removeRow(row_idx)
                continue
            data_rows.append({"ts": ts, "decoded": decoded})

        while table.rowCount() > max_rows:
            table.removeRow(0)
            data_rows.pop(0)

        table.setUpdatesEnabled(True)
        if batch:
            table.scrollToBottom()

    def flush_buffer(self):
        self._flush_buffer()

    def add_signal_instance(self, can_id, sig_name):
        self._plot.add_signal_instance(can_id, sig_name)

    def _clear(self):
        self._msg_buffer.clear()
        self._data_rows.clear()
        self._table.setRowCount(0)
        self._backend.clear_parsed_messages()
        self._plot.clear_data()
        self.cleared.emit()

    def _save_csv(self):
        if not self._data_rows:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Parsed Data", "", "CSV Files (*.csv)"
        )
        if not path:
            return

        fieldnames = ["Timestamp"]
        for can_id, sig_name, _sig in self._checked_signals:
            fieldnames.append(f"0x{can_id:03X}/{sig_name}")

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in self._data_rows:
                out = {"Timestamp": f"{row['ts']:.6f}"}
                for can_id, sig_name, _sig in self._checked_signals:
                    key = f"0x{can_id:03X}/{sig_name}"
                    val = row["decoded"].get(sig_name)
                    out[key] = str(val) if val is not None else ""
                writer.writerow(out)
