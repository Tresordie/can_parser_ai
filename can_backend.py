"""CAN bus abstraction — live acquisition and log file playback.

Performance model
-----------------
For log playback we parse the whole file *once* in a background thread and
build a per-signal index::

    self._signal_series: {sig_name: [np.ndarray t, np.ndarray v]}
    self._parsed_rows:   [(ts, decoded_dict, raw_info), ...]  # for the data table

Once parsed, replay only consumes the index (no re-decoding), and adding a
newly checked signal later is O(1) — the series is already decoded and is
handed straight to the plot via :meth:`get_signal_series`.
"""

import csv
import os
import time

import numpy as np
import can
from PyQt5.QtCore import QObject, pyqtSignal, QThread


def _plain_value(v):
    """Extract plain int/float/str from a cantools NamedSignalValue."""
    if hasattr(v, 'value'):
        return v.value
    return v


def _build_frame_id_map(dbc):
    """Pre-build {frame_id: message} for O(1) lookup during decode."""
    if dbc is None:
        return {}
    return {m.frame_id: m for m in dbc.messages}


class _FakeMsg:
    """Lightweight message-like object for signal CSV playback."""
    __slots__ = ('timestamp', 'arbitration_id')

    def __init__(self, timestamp):
        self.timestamp = timestamp
        self.arbitration_id = 0


def _parse_savvycan_frame_csv(filepath):
    """Parse a SavvyCAN frame-level CSV export into can.Message objects.

    Handles both formats:
    1. Individual byte columns: Time,ID,Extended,Dir,Bus,LEN,D1,...,D8
    2. Combined data column:  Time,ID,Extended,Dir,Bus,DLC,Data
       where Data is space-separated hex bytes like "00 01 02 03"

    Returns list of can.Message, or None if the file is not in this format.
    """
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        header_line = f.readline().strip()
        if not header_line:
            return None

        delim = '\t' if '\t' in header_line else ','
        header_cols = [c.strip() for c in next(csv.reader([header_line], delimiter=delim))]
        hl = [c.lower() for c in header_cols]
        if not hl[0].startswith("time") or not hl[1].startswith("id"):
            return None

        time_idx = 0
        id_idx = 1

        try:
            ext_idx = next(i for i, c in enumerate(hl)
                          if c in ("extended", "ext", "xtd", "ide"))
        except StopIteration:
            ext_idx = None

        try:
            dlc_idx = hl.index("len") if "len" in hl else hl.index("dlc")
        except ValueError:
            return None

        # Detect data layout: individual D1-D8 columns, or a single Data column
        data_cols = []
        combined_data_idx = None
        for i in range(dlc_idx + 1, len(hl)):
            c = hl[i]
            if c.startswith("d") and c[1:].isdigit():
                data_cols.append(i)
            elif c == "data":
                combined_data_idx = i
                break

        if not data_cols and combined_data_idx is None:
            return None

        messages = []
        for row in csv.reader(f, delimiter=delim):
            if not row:
                continue
            try:
                ts = float(row[time_idx])
                arb_id_str = row[id_idx].strip()
                try:
                    arb_id = int(arb_id_str, 16)
                except ValueError:
                    arb_id = int(arb_id_str)
                is_extended = False
                if ext_idx is not None and ext_idx < len(row):
                    v = row[ext_idx].strip().lower()
                    is_extended = v in ("true", "1", "extended")
                dlc = int(row[dlc_idx].strip())

                if combined_data_idx is not None:
                    # Space-separated hex bytes: "00 01 02" or "0x00 0x01 0x02"
                    hex_str = row[combined_data_idx].strip() if combined_data_idx < len(row) else ""
                    parts = hex_str.split()
                    data_bytes = [int(p, 16) for p in parts if p]
                else:
                    data_bytes = []
                    for di in data_cols:
                        if di >= len(row):
                            break
                        val = row[di].strip()
                        if val:
                            try:
                                data_bytes.append(int(val, 16))
                            except ValueError:
                                data_bytes.append(int(val))

                if len(data_bytes) < dlc:
                    data_bytes.extend([0] * (dlc - len(data_bytes)))
                data_bytes = data_bytes[:dlc]

                msg = can.Message(
                    timestamp=ts,
                    arbitration_id=arb_id,
                    is_extended_id=is_extended,
                    dlc=dlc,
                    data=data_bytes,
                )
                messages.append(msg)
            except (ValueError, IndexError):
                continue

        return messages if messages else None


def _parse_signal_csv(filepath):
    """Parse a SavvyCAN/Kvaser signal CSV file.

    Returns list of (timestamp, decoded_dict) tuples, or None if the file
    is not in the expected signal-CSV format.
    """
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            first_line = f.readline().strip()
            if first_line != "CSV signals":
                return None

            header = None
            for line in f:
                line = line.strip()
                if line.startswith("Timestamp,"):
                    header = next(csv.reader([line]))
                    break

            if header is None:
                return None

            signal_names = header[1:]  # column 0 is "Timestamp"

            parsed = []
            for row in csv.reader(f):
                if not row or row[0].strip() == "Counter":
                    continue
                try:
                    ts = float(row[0])
                except (ValueError, IndexError):
                    continue

                decoded = {}
                for i, val in enumerate(row[1:]):
                    if i >= len(signal_names):
                        break
                    val = val.strip()
                    if val:
                        try:
                            decoded[signal_names[i]] = float(val)
                        except ValueError:
                            decoded[signal_names[i]] = val

                if decoded:
                    parsed.append((ts, decoded))

            return parsed
    except Exception:
        return None


class CanBackend(QObject):
    message_received = pyqtSignal(object, object)
    # Batch form of message_received: list of (timestamp, decoded_dict)
    # rows. Live capture and log replay both emit through it, so the UI
    # pays one cross-thread hop per ~50 ms batch instead of one per frame.
    message_received_batch = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    stopped = pyqtSignal()
    # (done, total) parse progress for status-bar feedback
    parse_progress = pyqtSignal(int, int)
    # emitted once the whole log has been pre-decoded into the signal index
    parsed_ready = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bus = None
        self._notifier = None
        self._running = False
        self._dbc = None
        self._signal_cache = {}
        # Pre-decoded per-signal index (populated after a log parse):
        #   {sig_name: [np.ndarray(t), np.ndarray(v)]}
        self._signal_series = {}
        # Frame-level decoded rows for the data table: [(ts, decoded_dict), ...]
        self._parsed_rows = []
        self._frame_id_map = {}
        self._parse_thread = None
        self._playback_thread = None
        # filepath pending replay once parsing finishes
        self._pending_replay = None
        # Active acquisition mode: None | 'live' | 'playback'.
        # Drives what "Save CSV" exports: live → raw CAN Log (ASC),
        # playback → decoded signal CSV.
        self._mode = None
        # Raw can.Message list captured during live mode (for CAN Log export).
        self._raw_messages = []
        # Live-mode batch accumulator: frames are decoded in the Notifier
        # thread and emitted as one queued signal every ~64 frames / 50 ms.
        self._live_batch = []
        self._live_last_flush = time.monotonic()

    def set_dbc(self, dbc):
        self._dbc = dbc
        self._frame_id_map = _build_frame_id_map(dbc)

    def set_checked_signals(self, signal_list):
        self._signal_cache.clear()
        for can_id, sig_name, _sig_obj in signal_list:
            if can_id not in self._signal_cache:
                self._signal_cache[can_id] = []
            self._signal_cache[can_id].append(sig_name)

    # ------------------------------------------------------------------ #
    # Mode + raw message capture (drives Save-CSV behaviour)
    # ------------------------------------------------------------------ #
    def mode(self):
        """Current acquisition mode: None, 'live' or 'playback'."""
        return self._mode

    def raw_messages(self):
        """Raw can.Message list captured during live mode.

        Used to export a standard CAN Log (ASC) of everything received from
        the PCAN device. Playback mode does not populate this — it keeps the
        pre-decoded ``_parsed_rows`` instead.
        """
        return self._raw_messages

    def export_can_log(self, filepath):
        """Write all live-captured messages to a standard CAN log.

        Format is chosen by file extension: ``.asc`` → Vector ASC
        (the same format the input logs use), ``.csv`` → python-can CSV.
        Any other extension defaults to ASC.
        """
        if not self._raw_messages:
            return False
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".csv":
            writer_cls = can.CSVWriter
        else:
            writer_cls = can.ASCWriter
        with writer_cls(filepath) as writer:
            for msg in self._raw_messages:
                writer(msg)
        return True

    # ------------------------------------------------------------------ #
    # Pre-decoded signal index (the core of requirement #3)
    # ------------------------------------------------------------------ #
    def parsed_messages(self):
        """Return the complete pre-parsed dataset.

        Each entry is ``(timestamp, decoded_dict, raw_info)`` where
        ``raw_info`` is ``(can_id, dlc, data_bytes)`` for frame-level logs
        (ASC/BLF/SavvyCAN CSV) or ``None`` for signal CSV files.

        Kept for the data-table rebuild path. The plot uses
        :meth:`get_signal_series` instead.
        """
        return self._parsed_rows

    def clear_parsed_messages(self):
        self._parsed_rows.clear()
        self._signal_series.clear()

    def get_signal_series(self, sig_name):
        """Return ``(t_array, v_array)`` for a pre-decoded signal, or ``(None, None)``.

        O(1) after a log has been parsed — this is what makes adding a newly
        checked signal instant.
        """
        series = self._signal_series.get(sig_name)
        if series is None:
            return None, None
        return series[0], series[1]

    def all_parsed_signals(self):
        """Return ``[(can_id, sig_name), ...]`` for every signal in the index.

        Used when the user starts a log parse without checking any signal —
        we then treat *all* decoded signals as the selection so the table and
        plot show something instead of staying empty.
        """
        if not self._signal_series or self._dbc is None:
            return []
        # Build a reverse map sig_name -> frame_id from the DBC.
        sig_to_id = {}
        for msg in self._dbc.messages:
            for sig in msg.signals:
                sig_to_id.setdefault(sig.name, msg.frame_id)
        result = []
        seen = set()
        for sig_name in self._signal_series:
            can_id = sig_to_id.get(sig_name, 0)
            key = (can_id, sig_name)
            if key not in seen:
                seen.add(key)
                result.append(key)
        result.sort(key=lambda x: (x[0], x[1]))
        return result

    def export_parsed_csv(self, filepath, signals, progress_cb=None):
        """Write decoded signal values to a CSV file (high-performance).

        :param filepath:  destination CSV path.
        :param signals:   list of ``(can_id, sig_name, sig_obj)`` tuples —
                          the columns to export.
        :param progress_cb: optional ``callback(done, total)`` called every
                          ~5000 rows so the caller can report progress.
        :returns: number of rows written.

        Optimised for large logs (750k+ rows × 600+ signals):

        * column headers and sig_name list are pre-computed once,
        * the inner loop uses a pre-built ``sig_names`` list with direct
          ``dict.get`` lookups (no per-cell key formatting),
        * rows are written in batches to amortise I/O,
        * ``csv.writer.writerow`` with a plain list is far faster than
          ``DictWriter`` (no per-field dict construction).
        """
        parsed = self._parsed_rows
        if not parsed or not signals:
            return 0

        sig_names = [sig_name for _can_id, sig_name, _sig in signals]
        headers = ["Timestamp"] + [
            f"0x{can_id:03X}/{sig_name}"
            for can_id, sig_name, _sig in signals
        ]
        # Map every signal name to its column index so we can scatter only
        # the signals present in each row (most rows have just a handful).
        col_idx = {sn: i + 1 for i, sn in enumerate(sig_names)}
        n_cols = len(sig_names) + 1  # +1 for Timestamp
        total = len(parsed)
        _str = str  # local alias avoids global lookup in the hot loop

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for i, row in enumerate(parsed):
                ts = row[0]
                decoded = row[1]
                # Pre-fill an empty row, then set only the present signals.
                out = [""] * n_cols
                out[0] = f"{ts:.6f}"
                if decoded:
                    for sn, val in decoded.items():
                        ci = col_idx.get(sn)
                        if ci is not None:
                            out[ci] = _str(val)
                writer.writerow(out)
                if progress_cb is not None and i % 5000 == 0:
                    progress_cb(i, total)
        if progress_cb is not None:
            progress_cb(total, total)
        return total

    # ------------------------------------------------------------------ #
    # Live capture
    # ------------------------------------------------------------------ #
    def start_live(self, channel="PCAN_USBBUS1", bitrate=500000):
        try:
            self._bus = can.Bus(
                interface="pcan",
                channel=channel,
                bitrate=bitrate,
            )
            self._notifier = can.Notifier(self._bus, [self._on_live_message])
            self._running = True
            self._mode = 'live'
            # Fresh capture buffer for this live session.
            self._raw_messages = []
        except Exception as e:
            self.error_occurred.emit(f"Cannot open CAN device: {e}")

    # ------------------------------------------------------------------ #
    # Log playback: parse-first, then replay
    # ------------------------------------------------------------------ #
    def start_playback(self, filepath, speed=1.0):
        """Two-stage playback: parse the whole log first, then replay by timestamp."""
        try:
            self._running = True
            self._mode = 'playback'
            # Stop any previous parse/replay that may still be running so we
            # never orphan a QThread (which triggers "QThread: Destroyed
            # while thread is still running").
            self._stop_internal_threads()
            self._pending_replay = (filepath, speed)
            # Parse on a background thread; replay starts from _on_parsed_ready.
            self._parse_thread = _ParseThread(filepath, self._dbc, self._frame_id_map)
            self._parse_thread.progress.connect(self.parse_progress)
            self._parse_thread.error_occurred.connect(self.error_occurred)
            self._parse_thread.parsed_ready.connect(self._on_parsed_ready)
            # Clear the reference only after run() has fully returned, otherwise
            # Python may garbage-collect (and destroy) the QThread while it is
            # still executing — "QThread: Destroyed while thread is still running".
            self._parse_thread.finished.connect(self._on_parse_thread_finished)
            self._parse_thread.start()
        except Exception as e:
            self.error_occurred.emit(f"Cannot start playback: {e}")

    def _stop_internal_threads(self):
        """Stop and join any running parse/replay threads, dropping references.

        Disconnects signals *before* waiting so that the queued ``finished``
        signal cannot re-enter ``_on_playback_done`` / ``_on_parse_thread_finished``
        after we have already dropped the reference — this prevents the
        "QThread: Destroyed while thread is still running" warning and the
        double ``stopped`` emission that confuses the UI.
        """
        if self._parse_thread:
            t = self._parse_thread
            try:
                t.finished.disconnect(self._on_parse_thread_finished)
            except Exception:
                pass
            try:
                t.parsed_ready.disconnect(self._on_parsed_ready)
            except Exception:
                pass
            t.stop()
            t.wait(10000)
            t.deleteLater()
            self._parse_thread = None
        if self._playback_thread:
            t = self._playback_thread
            try:
                t.finished.disconnect(self._on_playback_done)
            except Exception:
                pass
            try:
                t.message_batch.disconnect(self._on_replay_batch)
            except Exception:
                pass
            t.stop()
            t.wait(10000)
            t.deleteLater()
            self._playback_thread = None

    def _on_parse_thread_finished(self):
        """Drop the parse-thread reference once run() has truly exited."""
        t = self._parse_thread
        if t is not None:
            t.deleteLater()
            self._parse_thread = None

    def _on_parsed_ready(self):
        """Called (via queued connection) once decoding finishes — take ownership of
        the index, then kick off replay on the main thread."""
        # Take the built index out of the thread. The thread object itself is
        # cleared by _on_parse_thread_finished once run() returns.
        t = self._parse_thread
        if t is not None:
            self._signal_series = t.take_series()
            self._parsed_rows = t.take_rows()
        self.parsed_ready.emit()

        # Schedule replay on the GUI/main thread.
        pending = self._pending_replay
        if pending is not None:
            self._pending_replay = None
            filepath, speed = pending
            self._begin_replay(filepath, speed)

    def _begin_replay(self, filepath, speed):
        """Start the timestamp-driven replay using the pre-decoded rows."""
        if not self._parsed_rows:
            self.error_occurred.emit("Log file contains no messages")
            self._running = False
            self.stopped.emit()
            return
        # Pass rows by reference — the replay thread only reads them.
        self._playback_thread = _ReplayThread(
            self._parsed_rows, speed, parent=self
        )
        self._playback_thread.message_batch.connect(self._on_replay_batch)
        self._playback_thread.finished.connect(self._on_playback_done)
        self._playback_thread.start()

    def _on_playback_done(self):
        # Clear the replay-thread reference now that run() has exited.
        # Guard: if stop() was already called, _running is False and the
        # reference has been cleared — nothing to do.
        if not self._running:
            return
        if self._playback_thread is not None:
            self._playback_thread.deleteLater()
            self._playback_thread = None
        self._running = False
        self.stopped.emit()

    def _on_live_message(self, msg):
        """Notifier-thread listener: buffer raw frames and emit decoded
        rows in batches (one queued signal per ~64 frames / 50 ms)."""
        if not self._running:
            return
        # Keep every raw frame so it can be exported as a CAN Log (ASC).
        if self._mode == "live":
            self._raw_messages.append(msg)
        self._live_batch.append(msg)
        if (len(self._live_batch) >= 64
                or time.monotonic() - self._live_last_flush >= 0.05):
            self._flush_live_batch()

    def _flush_live_batch(self):
        batch = self._live_batch
        if not batch:
            return
        self._live_batch = []
        self._live_last_flush = time.monotonic()
        rows = []
        for msg in batch:
            decoded = self._decode(msg)
            # None -> frame ID not checked; skip. An empty dict (mux
            # mismatch) is kept so the table preserves the timestamp.
            if decoded is not None:
                rows.append((msg.timestamp, decoded))
        if rows:
            self.message_received_batch.emit(rows)

    def _on_replay_batch(self, batch):
        """Forward a replay batch (list of (ts, decoded) rows) to the UI."""
        if not self._running:
            return
        self.message_received_batch.emit(batch)

    def _decode(self, msg):
        """Decode the *checked* signals of a live message.

        Note: cantools >=40 ``Signal`` objects have no ``.decode()``; we decode
        the whole message once and pick the checked signals out of the dict.

        Returns an empty dict ``{}`` (not ``None``) when the CAN ID matches
        but none of the checked signals appear in the decoded output — this
        happens with multiplexed messages when the frame's mux value doesn't
        match the checked signal's group.  Returning ``{}`` lets the UI
        preserve the timestamp row instead of silently dropping the frame.
        """
        if self._dbc is None:
            return None
        can_id = msg.arbitration_id
        wanted = self._signal_cache.get(can_id)
        if not wanted:
            return None
        msg_def = self._frame_id_map.get(can_id)
        if msg_def is None or len(msg.data) == 0:
            return None
        try:
            all_decoded = msg_def.decode(msg.data, decode_choices=False, allow_truncated=True)
        except Exception:
            return None
        decoded = {}
        for sig_name in wanted:
            if sig_name in all_decoded:
                decoded[sig_name] = _plain_value(all_decoded[sig_name])
        # Return {} (not None) so mux-mismatched frames still register a
        # timestamp row in the data table.
        return decoded

    def stop(self):
        self._running = False
        # Join parse/replay threads (with a generous timeout) before dropping
        # references — never orphan a running QThread.
        self._stop_internal_threads()
        if self._notifier:
            self._notifier.stop()
            self._notifier = None
        # Flush any decoded frames still sitting in the live batch.
        self._flush_live_batch()
        if self._bus:
            self._bus.shutdown()
            self._bus = None
        self.stopped.emit()


class _ParseThread(QThread):
    """Background full-file decode that builds the per-signal index.

    Runs once per playback; emits coarse progress and hands off the built
    index via :meth:`take_series` / :meth:`take_rows`.
    """

    parsed_ready = pyqtSignal()
    progress = pyqtSignal(int, int)
    error_occurred = pyqtSignal(str)

    def __init__(self, filepath, dbc, frame_id_map, parent=None):
        super().__init__(parent)
        self._filepath = filepath
        self._dbc = dbc
        self._frame_id_map = frame_id_map
        self._stop = False
        # Index built during run():
        #   {sig_name: [list_of_t, list_of_v]}
        self._series = {}
        self._rows = []

    def stop(self):
        self._stop = True

    def take_series(self):
        series = self._series
        self._series = {}
        return series

    def take_rows(self):
        rows = self._rows
        self._rows = []
        return rows

    def run(self):
        # Fast path: signal CSV (already decoded, no DBC needed).
        signal_rows = _parse_signal_csv(self._filepath)
        if signal_rows is not None:
            if self._stop:
                return
            self._build_index_from_rows(signal_rows)
            self._emit_progress(len(signal_rows), len(signal_rows))
            self.parsed_ready.emit()
            return

        # Frame-level sources: SavvyCAN CSV, then python-can LogReader.
        try:
            messages = _parse_savvycan_frame_csv(self._filepath)
        except Exception:
            messages = None

        if messages is None:
            try:
                reader = can.LogReader(self._filepath)
                messages = list(reader)
            except Exception as e:
                self.error_occurred.emit(f"Failed to read log file: {e}")
                return

        if not messages:
            self.error_occurred.emit("Log file contains no messages")
            return

        # Single pass: decode each matching frame and scatter into the index.
        frame_id_map = self._frame_id_map
        series = self._series
        rows = self._rows
        total = len(messages)
        step = max(1, total // 100)
        # (frame_id, payload) -> decoded dict; recorded logs repeat
        # identical frames often, so a cache hit skips the pure-Python
        # cantools decode. Cached dicts are only ever read downstream.
        decode_cache = {}
        cache_max = 200000

        for i, msg in enumerate(messages):
            if self._stop:
                return
            ts = msg.timestamp
            msg_def = frame_id_map.get(msg.arbitration_id)
            decoded = None
            if msg_def is not None and len(msg.data) > 0:
                data_b = bytes(msg.data)
                decoded = decode_cache.get((msg.arbitration_id, data_b))
                if decoded is None:
                    try:
                        decoded = msg_def.decode(data_b, decode_choices=False,
                                                 allow_truncated=True)
                    except Exception:
                        decoded = None
                    if decoded and len(decode_cache) < cache_max:
                        decode_cache[(msg.arbitration_id, data_b)] = decoded
            if decoded:
                for sig_name, v in decoded.items():
                    lst = series.get(sig_name)
                    if lst is None:
                        lst = [[], []]
                        series[sig_name] = lst
                    lst[0].append(ts)
                    lst[1].append(_plain_value(v))
                rows.append((ts, decoded, (msg.arbitration_id, msg.dlc, bytes(msg.data))))
            if i % step == 0:
                self._emit_progress(i, total)

        self._emit_progress(total, total)
        self.parsed_ready.emit()

    def _build_index_from_rows(self, signal_rows):
        """Build the per-signal index from already-decoded (ts, dict) rows.

        Signal CSV files have no raw frame bytes, so the raw-info slot is
        ``None`` (the raw-data table view is only available for frame-level
        logs such as ASC/BLF).
        """
        series = self._series
        rows = self._rows
        for ts, decoded in signal_rows:
            if self._stop:
                return
            for sig_name, v in decoded.items():
                lst = series.get(sig_name)
                if lst is None:
                    lst = [[], []]
                    series[sig_name] = lst
                lst[0].append(ts)
                lst[1].append(v)
            rows.append((ts, decoded, None))

    def _emit_progress(self, done, total):
        # Convert per-signal python lists to numpy arrays lazily — done once
        # at the end so the hot loop stays allocation-free.
        if done >= total:
            for sig_name, lst in self._series.items():
                self._series[sig_name] = [
                    np.asarray(lst[0], dtype=np.float64),
                    np.asarray(lst[1], dtype=np.float64),
                ]
        self.progress.emit(done, total)


class _ReplayThread(QThread):
    """Timestamp-driven replay that consumes already-decoded rows.

    Rows due within each ~50 ms wall-clock window are emitted as one
    batch, so a dense log (or a high speed factor) costs one cross-thread
    hop per window instead of one per frame.
    """

    message_batch = pyqtSignal(list)

    _WINDOW_S = 0.05     # collection window per batch (wall clock)
    _MAX_BATCH = 5000    # hard cap on rows per emitted batch

    def __init__(self, rows, speed=1.0, parent=None):
        super().__init__(parent)
        self._rows = rows
        self._speed = speed
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        rows = self._rows
        if not rows:
            return
        base_ts = rows[0][0]
        base_wall = time.time()
        n = len(rows)
        speed = self._speed
        i = 0
        while i < n and not self._stop:
            now = time.time()
            batch = []
            # Collect every row that comes due within the next window.
            while i < n and len(batch) < self._MAX_BATCH:
                target = base_wall + (rows[i][0] - base_ts) / speed
                if target - now > self._WINDOW_S:
                    break
                batch.append((rows[i][0], rows[i][1]))
                i += 1
            if batch:
                self.message_batch.emit(batch)
            if i >= n or self._stop:
                return
            # Sleep until the next row is due, in 100 ms chunks so stop()
            # stays responsive across large timestamp gaps.
            target = base_wall + (rows[i][0] - base_ts) / speed
            delay = target - time.time()
            if delay > 0.001:
                remaining_ms = int(delay * 1000)
                while remaining_ms > 0 and not self._stop:
                    chunk = min(remaining_ms, 100)
                    self.msleep(chunk)
                    self.msleep(chunk)
                    remaining_ms -= chunk