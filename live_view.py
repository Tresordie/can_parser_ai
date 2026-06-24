"""Live data display — text table and signal plot tabs."""

import csv
import os

import can
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QPushButton, QFileDialog, QHeaderView, QLabel,
    QSpinBox, QMessageBox,
)
from signal_plot import SignalPlot


class LiveView(QWidget):
    cleared = pyqtSignal()
    # Emitted when the user clicks a legend label in the Signal Plot.
    # Carries (can_id, sig_name) so the host can select it in the tree.
    signal_label_clicked = pyqtSignal(int, str)
    # Emitted with a status message (e.g. during CSV export) for the status bar.
    status_message = pyqtSignal(str)
    MAX_TABLE_ROWS = 1000
    FLUSH_INTERVAL_MS = 100

    def __init__(self, backend, dbc_loader, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._dbc_loader = dbc_loader

        self._data_rows = []
        self._checked_signals = []        # signals drawn on the Signal Plot
        self._table_signals = []          # signals shown as table columns
        self._raw_view = False            # True → table shows raw CAN frames
        self._csv_export_thread = None    # background CSV writer thread

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()

        self._table = QTableWidget()
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabs.addTab(self._table, "Data Table")

        self._plot = SignalPlot()
        self._plot.signal_label_clicked.connect(self.signal_label_clicked)
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
        # Blitting keeps each frame cheap enough for ~4 Hz refresh, which
        # makes live capture and log replay feel responsive.
        self._plot_timer.start(250)

    def load_parsed_series(self, checked_signals=None):
        """Bulk-load parsed data once a log finishes decoding.

        Two display modes driven by whether the user has checked any signal:

        * **No signal checked** — the Data Table shows raw CAN message data
          (Timestamp, CAN ID, DLC, raw data bytes). The Signal Plot stays
          empty. This gives an immediate overview of every frame without
          needing to pick signals first.
        * **Signals checked** — the Data Table shows the decoded values of
          the checked signals, and the Signal Plot draws them. Newly checked
          signals load instantly from the pre-decoded backend index.

        Called once a log finishes parsing (and on any later re-check).
        """
        checked = checked_signals if checked_signals is not None else self._checked_signals
        self._checked_signals = checked

        # ── Signal Plot: only the checked signals ──
        self._plot.set_signals(checked)
        for can_id, sig_name, _sig in checked:
            t_arr, v_arr = self._backend.get_signal_series(sig_name)
            if t_arr is not None and t_arr.size:
                self._plot.set_series(can_id, sig_name, t_arr, v_arr)
        self._plot.update_plot()

        # ── Data Table ──
        if not checked:
            # Raw CAN message view: Timestamp | CAN ID | DLC | Data
            self._table_signals = []  # no decoded-signal columns
            self._raw_view = True
            headers = ["Timestamp", "CAN ID", "DLC", "Data"]
            self._table.setColumnCount(len(headers))
            self._table.setHorizontalHeaderLabels(headers)
            self._table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeToContents)
            self._data_rows = [
                {"ts": ts, "raw": raw}
                for ts, _d, raw in self._backend.parsed_messages()
                if raw is not None
            ]
        else:
            # Decoded signal view: Timestamp | 0xID/SigName | ...
            self._raw_view = False
            self._table_signals = list(checked)
            headers = ["Timestamp"]
            for can_id, sig_name, _sig in checked:
                headers.append(f"0x{can_id:03X}/{sig_name}")
            self._table.setColumnCount(len(headers))
            self._table.setHorizontalHeaderLabels(headers)
            self._table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeToContents)
            self._data_rows = [
                {"ts": ts, "decoded": d}
                for ts, d, _raw in self._backend.parsed_messages()
                if d is not None
            ]

        self._rebuild_table()

    def refresh_signals(self, checked_signals):
        """Update the Signal Plot and Data Table when the user checks/unchecks.

        Newly checked signals are loaded instantly from the pre-decoded
        backend index (O(1) per signal) — no re-parsing needed.

        Table mode transitions:
        * raw view (no selection) → decoded view when the first signal is
          checked,
        * decoded view → raw view when the last signal is unchecked,
        * decoded view → stays decoded view when signals are added/removed
          (columns are rebuilt from the new selection).
        """
        old_names = {sig_name for _, sig_name, _ in self._checked_signals}
        new_names = {sig_name for _, sig_name, _ in checked_signals}
        added = new_names - old_names

        self._checked_signals = checked_signals

        # ── Signal Plot ──
        self._plot.set_signals(checked_signals)
        if added:
            # O(1) per signal: pull the pre-decoded series straight from the
            # backend index instead of re-scanning every parsed row.
            added_can_map = {}
            for can_id, sig_name, _sig in checked_signals:
                if sig_name in added:
                    added_can_map[sig_name] = can_id
            for sig_name in added:
                t_arr, v_arr = self._backend.get_signal_series(sig_name)
                if t_arr is not None and t_arr.size:
                    self._plot.set_series(
                        added_can_map[sig_name], sig_name, t_arr, v_arr
                    )
        self._plot.update_plot()

        # ── Data Table ──
        if checked_signals:
            # Switch to (or stay in) decoded view with the current selection.
            self._raw_view = False
            self._table_signals = list(checked_signals)
            headers = ["Timestamp"]
            for can_id, sig_name, _sig in checked_signals:
                headers.append(f"0x{can_id:03X}/{sig_name}")
            self._table.setColumnCount(len(headers))
            self._table.setHorizontalHeaderLabels(headers)
            self._table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeToContents)
            # Rebuild _data_rows from the decoded dict if we were in raw view.
            if not self._data_rows or "decoded" not in self._data_rows[0]:
                self._data_rows = [
                    {"ts": ts, "decoded": d}
                    for ts, d, _raw in self._backend.parsed_messages()
                    if d is not None
                ]
            self._rebuild_table()
        elif self._backend.parsed_messages():
            # No signal checked but a log was parsed → raw CAN frame view.
            self._raw_view = True
            self._table_signals = []
            headers = ["Timestamp", "CAN ID", "DLC", "Data"]
            self._table.setColumnCount(len(headers))
            self._table.setHorizontalHeaderLabels(headers)
            self._table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeToContents)
            self._data_rows = [
                {"ts": ts, "raw": raw}
                for ts, _d, raw in self._backend.parsed_messages()
                if raw is not None
            ]
            self._rebuild_table()

    def _rebuild_table(self):
        """Rebuild the data table from ``_data_rows``.

        On large logs (e.g. 750k frames) populating the table row-by-row
        freezes the Qt event loop for seconds, which made it look like the
        table was empty — especially for multiplexed signals, where the plot
        (driven by the O(1) numpy index) rendered instantly but the table
        never finished. To keep the UI responsive we:

        * cap the visible rows at ``MAX_TABLE_ROWS`` (showing the most recent
          rows; ``_data_rows`` still keeps the full dataset for CSV export),
        * allocate the row count in one shot instead of calling
          ``insertRow()`` per row (each call triggers a model/view update),
        * silence signals and updates while filling the cells.
        """
        table = self._table
        table.setUpdatesEnabled(False)
        table.blockSignals(True)
        table.setRowCount(0)

        # Show only the most recent MAX_TABLE_ROWS so the table stays
        # responsive on large logs. _data_rows keeps the full dataset for
        # CSV export.
        visible = self._data_rows[-self.MAX_TABLE_ROWS:]
        table.setRowCount(len(visible))

        if self._raw_view:
            # Raw CAN frame view: Timestamp | CAN ID | DLC | Data (hex bytes)
            for row_idx, row in enumerate(visible):
                table.setItem(row_idx, 0,
                              QTableWidgetItem(f"{row['ts']:.6f}"))
                raw = row.get("raw")
                if raw is not None:
                    can_id, dlc, data = raw
                    table.setItem(row_idx, 1,
                                  QTableWidgetItem(f"0x{can_id:03X}"))
                    table.setItem(row_idx, 2, QTableWidgetItem(str(dlc)))
                    hex_str = " ".join(f"{b:02X}" for b in data[:dlc])
                    table.setItem(row_idx, 3, QTableWidgetItem(hex_str))
        else:
            # Decoded signal view
            table_signals = self._table_signals
            for row_idx, row in enumerate(visible):
                table.setItem(row_idx, 0,
                              QTableWidgetItem(f"{row['ts']:.6f}"))
                for col, (can_id, sig_name, _sig) in enumerate(table_signals, 1):
                    val = row["decoded"].get(sig_name)
                    if val is not None:
                        table.setItem(row_idx, col, QTableWidgetItem(str(val)))

        table.blockSignals(False)
        table.setUpdatesEnabled(True)
        table.scrollToBottom()

    def _on_message(self, msg, decoded):
        if not self._checked_signals or decoded is None:
            return
        # decoded may be {} for multiplexed messages where the frame's mux
        # value doesn't match any checked signal — still queue it so the
        # timestamp row is preserved in the data table.
        self._msg_buffer.append((msg, decoded))

    def _flush_buffer(self):
        if not self._msg_buffer:
            return

        batch = self._msg_buffer
        self._msg_buffer = []

        table = self._table
        data_rows = self._data_rows
        table_signals = self._table_signals
        plot = self._plot
        max_rows = self.MAX_TABLE_ROWS

        table.setUpdatesEnabled(False)
        for msg, decoded in batch:
            ts = msg.timestamp
            row_idx = table.rowCount()
            table.insertRow(row_idx)
            table.setItem(row_idx, 0, QTableWidgetItem(f"{ts:.6f}"))

            # Table columns cover every decoded signal; the plot only gets
            # points for the checked signals.
            for col, (can_id, sig_name, _sig) in enumerate(table_signals, 1):
                val = decoded.get(sig_name)
                if val is not None:
                    table.setItem(row_idx, col, QTableWidgetItem(str(val)))

            for can_id, sig_name, _sig in self._checked_signals:
                val = decoded.get(sig_name)
                if val is not None:
                    plot.add_point(ts, can_id, sig_name, val)

            # Always keep the row (even when has_value is False) so the
            # timestamp sequence stays continuous for multiplexed messages
            # where some frames don't match the checked mux group.
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
        self._table_signals = []
        self._raw_view = False
        self._backend.clear_parsed_messages()
        self._plot.clear_data()
        self.cleared.emit()

    def _save_csv(self):
        """Save button — behaviour depends on the active acquisition mode.

        * ``live``     → export every raw CAN message received from the PCAN
          device as a standard CAN Log (Vector ASC by default, CSV if the
          user picks a ``.csv`` extension).
        * ``playback`` → export the decoded values of the checked signals as
          a CSV (the historical behaviour).
        """
        mode = self._backend.mode()
        if mode == 'live':
            self._save_can_log()
        else:
            # playback (or no explicit mode but data present) → decoded CSV
            self._save_parsed_csv()

    def _save_can_log(self):
        """Live mode: export all raw CAN messages as a standard CAN log."""
        raw = self._backend.raw_messages()
        if not raw:
            QMessageBox.information(
                self, "Save CAN Log",
                "No CAN messages have been received yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save CAN Log", "",
            "CAN ASC Log (*.asc);;CSV (*.csv);;All (*)"
        )
        if not path:
            return
        try:
            ok = self._backend.export_can_log(path)
        except Exception as e:
            QMessageBox.critical(self, "Save CAN Log", f"Failed to save: {e}")
            return
        if ok:
            QMessageBox.information(
                self, "Save CAN Log",
                f"Saved {len(raw)} messages to:\n{path}")
        else:
            QMessageBox.information(
                self, "Save CAN Log", "No messages to save.")

    def _save_parsed_csv(self):
        """Playback mode: export decoded signal values as CSV.

        Always exports the *parsed* (decoded) signal data — never the raw
        bytes — so the user gets a usable signal spreadsheet regardless of
        whether the table is currently in raw or decoded view:

        * Raw view (no signal checked) → every signal decoded from the log.
        * Decoded view (signals checked) → the checked signals.

        The write runs on a background thread so the UI stays responsive
        on large logs (750k+ rows × 600+ signals).
        """
        parsed = self._backend.parsed_messages()
        if not parsed:
            QMessageBox.information(
                self, "Save Parsed Data", "No parsed data to save.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Parsed Data", "", "CSV Files (*.csv)"
        )
        if not path:
            return

        # Determine which signals to export.
        if self._raw_view or not self._checked_signals:
            # No selection → export every decoded signal in the index.
            signals = [
                (can_id, sig_name, None)
                for can_id, sig_name in self._backend.all_parsed_signals()
            ]
        else:
            signals = self._table_signals or self._checked_signals

        if not signals:
            QMessageBox.information(
                self, "Save Parsed Data", "No signals to export.")
            return

        # Disable the button while the export runs.
        self._save_btn.setEnabled(False)
        self._save_btn.setText("Saving...")

        self._csv_export_thread = _CsvExportThread(
            self._backend, path, signals, parent=self
        )
        self._csv_export_thread.progress.connect(self._on_csv_progress)
        self._csv_export_thread.finished_ok.connect(self._on_csv_finished)
        self._csv_export_thread.start()

    def _on_csv_progress(self, done, total):
        if total > 0:
            self.status_message.emit(
                f"Saving CSV... {done}/{total} ({done * 100 // total}%)")

    def _on_csv_finished(self, ok, row_count, error):
        self._save_btn.setEnabled(True)
        self._save_btn.setText("Save CSV")
        # Let the QThread fully finish before dropping the reference.
        t = self._csv_export_thread
        if t is not None:
            t.wait(2000)
            t.deleteLater()
        self._csv_export_thread = None
        if ok:
            self.status_message.emit(f"CSV saved: {row_count} rows")
            QMessageBox.information(
                self, "Save Parsed Data",
                f"Saved {row_count} rows to CSV.")
        else:
            self.status_message.emit(f"CSV save failed: {error}")
            QMessageBox.critical(self, "Save Parsed Data", f"Failed: {error}")


class _CsvExportThread(QThread):
    """Background thread that writes the decoded signal CSV.

    Large logs (750k+ rows × 600+ signals) take many seconds to write — doing
    it on the GUI thread froze the whole app. This thread calls
    :meth:`CanBackend.export_parsed_csv` (an optimised writer) and reports
    coarse progress so the status bar can show how far along it is.
    """

    progress = pyqtSignal(int, int)   # (done, total)
    finished_ok = pyqtSignal(bool, int, str)  # (ok, row_count, error)

    def __init__(self, backend, filepath, signals, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._filepath = filepath
        self._signals = signals

    def run(self):
        try:
            count = self._backend.export_parsed_csv(
                self._filepath, self._signals,
                progress_cb=lambda d, t: self.progress.emit(d, t),
            )
            self.finished_ok.emit(True, count, "")
        except Exception as e:
            self.finished_ok.emit(False, 0, str(e))
