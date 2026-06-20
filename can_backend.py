"""CAN bus abstraction — live acquisition and log file playback."""

import csv
import time
import can
from PyQt5.QtCore import QObject, pyqtSignal, QThread


def _plain_value(v):
    """Extract plain int/float/str from a cantools NamedSignalValue."""
    if hasattr(v, 'value'):
        return v.value
    return v


def _decode_all(dbc, msg):
    """Decode every signal from a message regardless of checked state."""
    if dbc is None:
        return None
    try:
        msg_def = dbc.get_message_by_frame_id(msg.arbitration_id)
        if len(msg.data) < msg_def.length:
            return None
        all_decoded = msg_def.decode(msg.data)
        return {sig_name: _plain_value(v) for sig_name, v in all_decoded.items()}
    except Exception:
        return None


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
    error_occurred = pyqtSignal(str)
    stopped = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bus = None
        self._notifier = None
        self._running = False
        self._dbc = None
        self._signal_cache = {}
        self._playback_thread = None
        self._parsed_messages = []

    def set_dbc(self, dbc):
        self._dbc = dbc

    def set_checked_signals(self, signal_list):
        self._signal_cache.clear()
        for can_id, sig_name, _sig_obj in signal_list:
            if can_id not in self._signal_cache:
                self._signal_cache[can_id] = []
            self._signal_cache[can_id].append(sig_name)

    def parsed_messages(self):
        """Return the complete pre-parsed dataset: list of (timestamp, decoded_dict)."""
        return self._parsed_messages

    def clear_parsed_messages(self):
        self._parsed_messages.clear()

    def start_live(self, channel="PCAN_USBBUS1", bitrate=500000):
        try:
            self._bus = can.Bus(
                interface="pcan",
                channel=channel,
                bitrate=bitrate,
            )
            self._notifier = can.Notifier(self._bus, [self._on_message])
            self._running = True
        except Exception as e:
            self.error_occurred.emit(f"Cannot open CAN device: {e}")

    def start_playback(self, filepath, speed=1.0):
        try:
            self._running = True
            self._playback_thread = _PlaybackThread(filepath, self._dbc, speed)
            self._playback_thread.message_ready.connect(self._on_message)
            self._playback_thread.message_with_data.connect(self._on_message_with_data)
            self._playback_thread.error_occurred.connect(self.error_occurred)
            self._playback_thread.finished.connect(self._on_playback_done)
            self._playback_thread.parsed_ready.connect(self._on_parsed_ready)
            self._playback_thread.start()
        except Exception as e:
            self.error_occurred.emit(f"Cannot start playback: {e}")

    def _on_parsed_ready(self, parsed):
        self._parsed_messages = parsed

    def _on_playback_done(self):
        self._running = False
        self.stopped.emit()

    def _on_message(self, msg):
        if not self._running:
            return
        decoded = self._decode(msg)
        self.message_received.emit(msg, decoded)

    def _on_message_with_data(self, msg, decoded):
        if not self._running:
            return
        self.message_received.emit(msg, decoded)

    def _decode(self, msg):
        if self._dbc is None:
            return None
        can_id = msg.arbitration_id
        if can_id not in self._signal_cache:
            return None
        try:
            msg_def = self._dbc.get_message_by_frame_id(can_id)
            if len(msg.data) < msg_def.length:
                return None
            decoded = {}
            for sig_name in self._signal_cache[can_id]:
                sig = msg_def.get_signal_by_name(sig_name)
                decoded[sig_name] = _plain_value(sig.decode(msg.data))
            return decoded if decoded else None
        except Exception:
            return None

    def stop(self):
        self._running = False
        if self._playback_thread:
            self._playback_thread.stop()
            self._playback_thread.wait(2000)
            self._playback_thread = None
        if self._notifier:
            self._notifier.stop()
            self._notifier = None
        if self._bus:
            self._bus.shutdown()
            self._bus = None
        self.stopped.emit()


class _PlaybackThread(QThread):
    message_ready = pyqtSignal(object)
    message_with_data = pyqtSignal(object, object)
    parsed_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, filepath, dbc, speed=1.0, parent=None):
        super().__init__(parent)
        self._filepath = filepath
        self._dbc = dbc
        self._speed = speed
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        parsed = _parse_signal_csv(self._filepath)
        if parsed is not None:
            if self._stop:
                return
            self.parsed_ready.emit(parsed)
            base_ts = parsed[0][0]
            base_wall = time.time()
            for ts, decoded in parsed:
                if self._stop:
                    return
                offset = ts - base_ts
                target = base_wall + offset / self._speed
                delay = target - time.time()
                if delay > 0.001:
                    self.msleep(int(delay * 1000))
                self.message_with_data.emit(_FakeMsg(ts), decoded)
            return

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

        parsed = []
        for msg in messages:
            if self._stop:
                return
            decoded = _decode_all(self._dbc, msg)
            parsed.append((msg.timestamp, decoded))

        self.parsed_ready.emit(parsed)

        base_ts = parsed[0][0]
        base_wall = time.time()

        for ts, decoded in parsed:
            if self._stop:
                return
            offset = ts - base_ts
            target = base_wall + offset / self._speed
            delay = target - time.time()
            if delay > 0.001:
                self.msleep(int(delay * 1000))
            self.message_with_data.emit(_FakeMsg(ts), decoded)
