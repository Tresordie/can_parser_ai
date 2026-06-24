"""DBC file loading and signal tree model — signals default unchecked.

Multiplexed signals are grouped under ``[mux=N]`` nodes so the user can
see which signals share a multiplexor value.  The tree structure is:

    Message (0xID)
    ├── MultiplexorSignal  [MUX]
    ├── [mux=0]  SignalA / SignalB        ← non-muxed signals under mux=0
    ├── [mux=10] SignalC / SignalD        ← mux-dependent group
    ├── [mux=11] SignalE / SignalF
    └── PlainSignal                       ← non-muxed message, no grouping
"""

from collections import defaultdict

import cantools
from PyQt5.QtCore import Qt, QObject, pyqtSignal
from PyQt5.QtGui import QStandardItemModel, QStandardItem


class DbcLoader(QObject):
    dbc_loaded = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    CHECKED_ROLE = Qt.UserRole + 1
    SIGNAL_OBJ_ROLE = Qt.UserRole + 2
    CAN_ID_ROLE = Qt.UserRole + 3

    ITEM_TYPE_MESSAGE = 1
    ITEM_TYPE_SIGNAL = 2
    ITEM_TYPE_MUX_GROUP = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db = None
        self._model = QStandardItemModel()
        self._model.setHorizontalHeaderLabels(["Messages / Signals"])
        self._signal_items = {}
        self._message_items = {}
        self._cascading = False

    @property
    def model(self):
        return self._model

    @property
    def database(self):
        return self._db

    # ------------------------------------------------------------------ #
    # DBC loading
    # ------------------------------------------------------------------ #
    def load(self, filepath):
        try:
            self._db = cantools.database.load_file(filepath)
            self._model.clear()
            self._model.setHorizontalHeaderLabels(["Messages / Signals"])
            self._signal_items.clear()
            self._message_items.clear()

            for msg in self._db.messages:
                msg_item = QStandardItem(f"{msg.name} (0x{msg.frame_id:03X})")
                msg_item.setFlags(msg_item.flags() | Qt.ItemIsUserCheckable)
                msg_item.setCheckState(Qt.Unchecked)
                msg_item.setData(self.ITEM_TYPE_MESSAGE, self.CHECKED_ROLE)
                msg_item.setData(msg.frame_id, self.CAN_ID_ROLE)
                msg_item.setData(msg, self.SIGNAL_OBJ_ROLE)
                self._model.appendRow(msg_item)
                self._message_items[msg.frame_id] = msg_item

                # Classify signals: multiplexor / mux-dependent / plain
                has_mux = any(
                    s.is_multiplexer or s.multiplexer_ids is not None
                    for s in msg.signals
                )

                if has_mux:
                    self._build_mux_tree(msg, msg_item)
                else:
                    # Simple message — flat signal list
                    for sig in msg.signals:
                        self._add_signal_item(msg_item, msg.frame_id, sig)

            self.dbc_loaded.emit(self._db)
            return True
        except Exception as e:
            self._model.clear()
            self.error_occurred.emit(f"Failed to load DBC: {e}")
            return False

    def _build_mux_tree(self, msg, msg_item):
        """Build a grouped tree for a multiplexed message."""
        # 1. Add the multiplexor signal first, marked with [MUX]
        for sig in msg.signals:
            if sig.is_multiplexer:
                mux_label = f"{sig.name}  [MUX]"
                self._add_signal_item(msg_item, msg.frame_id, sig,
                                      label=mux_label)
                break

        # 2. Group mux-dependent signals by their mux_id
        mux_groups = defaultdict(list)  # mux_id -> [Signal, ...]
        plain_signals = []              # non-muxed signals in this message
        for sig in msg.signals:
            if sig.is_multiplexer:
                continue
            if sig.multiplexer_ids is not None:
                for mid in sig.multiplexer_ids:
                    mux_groups[mid].append(sig)
            else:
                plain_signals.append(sig)

        # 3. Add mux groups as collapsible [mux=N] nodes
        for mid in sorted(mux_groups):
            signals = mux_groups[mid]
            group_item = QStandardItem(f"[mux={mid}]  ({len(signals)} signals)")
            group_item.setFlags(
                group_item.flags() & ~Qt.ItemIsUserCheckable
            )
            group_item.setData(self.ITEM_TYPE_MUX_GROUP, self.CHECKED_ROLE)
            group_item.setData(msg.frame_id, self.CAN_ID_ROLE)
            msg_item.appendRow(group_item)

            for sig in signals:
                self._add_signal_item(group_item, msg.frame_id, sig)

        # 4. Add any plain (non-muxed) signals at the message level
        for sig in plain_signals:
            self._add_signal_item(msg_item, msg.frame_id, sig)

    def _add_signal_item(self, parent_item, can_id, sig, label=None):
        """Create a checkable signal item and register it."""
        sig_item = QStandardItem(label or sig.name)
        sig_item.setFlags(sig_item.flags() | Qt.ItemIsUserCheckable)
        sig_item.setCheckState(Qt.Unchecked)
        sig_item.setData(self.ITEM_TYPE_SIGNAL, self.CHECKED_ROLE)
        sig_item.setData(can_id, self.CAN_ID_ROLE)
        sig_item.setData(sig, self.SIGNAL_OBJ_ROLE)
        parent_item.appendRow(sig_item)
        key = (can_id, sig.name)
        self._signal_items[key] = sig_item

    # ------------------------------------------------------------------ #
    # Check-state cascading (3-level: message → mux_group → signal)
    # ------------------------------------------------------------------ #
    def cascade_check_state(self, item):
        if self._cascading:
            return
        self._cascading = True
        item_type = item.data(self.CHECKED_ROLE)
        state = item.checkState()

        if item_type == self.ITEM_TYPE_MESSAGE:
            # Cascade down to all children, including mux_group sub-children
            self._cascade_down(item, state)

        elif item_type == self.ITEM_TYPE_MUX_GROUP:
            # Cascade to all signals inside this group
            self._cascade_down(item, state)
            # Update parent message check state
            self._update_parent_check(item.parent())

        elif item_type == self.ITEM_TYPE_SIGNAL:
            parent = item.parent()
            if parent is None:
                pass
            elif parent.data(self.CHECKED_ROLE) == self.ITEM_TYPE_MUX_GROUP:
                # Signal inside a mux group → update mux group, then message
                self._update_parent_check(parent)
                self._update_parent_check(parent.parent())
            elif parent.data(self.CHECKED_ROLE) == self.ITEM_TYPE_MESSAGE:
                # Direct child of message → update message
                self._update_parent_check(parent)

        self._cascading = False

    def _cascade_down(self, parent, state):
        """Recursively set check state on all signal descendants."""
        for r in range(parent.rowCount()):
            child = parent.child(r)
            child_type = child.data(self.CHECKED_ROLE)
            if child_type == self.ITEM_TYPE_MUX_GROUP:
                self._cascade_down(child, state)
            else:
                child.setCheckState(state)

    def _update_parent_check(self, parent):
        """Update a parent item's check state based on its children."""
        if parent is None:
            return
        all_checked = all(
            self._is_signal_checked(parent.child(r))
            for r in range(parent.rowCount())
        )
        all_unchecked = all(
            self._is_signal_unchecked(parent.child(r))
            for r in range(parent.rowCount())
        )
        if all_checked:
            parent.setCheckState(Qt.Checked)
        elif all_unchecked:
            parent.setCheckState(Qt.Unchecked)
        else:
            parent.setCheckState(Qt.PartiallyChecked)

    def _is_signal_checked(self, item):
        """Return True if the item represents a fully-checked signal branch."""
        item_type = item.data(self.CHECKED_ROLE)
        if item_type == self.ITEM_TYPE_MUX_GROUP:
            return all(
                self._is_signal_checked(item.child(r))
                for r in range(item.rowCount())
            )
        return item.checkState() == Qt.Checked

    def _is_signal_unchecked(self, item):
        """Return True if the item represents a fully-unchecked signal branch."""
        item_type = item.data(self.CHECKED_ROLE)
        if item_type == self.ITEM_TYPE_MUX_GROUP:
            return all(
                self._is_signal_unchecked(item.child(r))
                for r in range(item.rowCount())
            )
        return item.checkState() == Qt.Unchecked

    # ------------------------------------------------------------------ #
    # Select / deselect all
    # ------------------------------------------------------------------ #
    def select_all(self):
        self._cascading = True
        for _can_id, msg_item in self._message_items.items():
            self._cascade_down(msg_item, Qt.Checked)
            msg_item.setCheckState(Qt.Checked)
        self._cascading = False

    def deselect_all(self):
        self._cascading = True
        for _can_id, msg_item in self._message_items.items():
            self._cascade_down(msg_item, Qt.Unchecked)
            msg_item.setCheckState(Qt.Unchecked)
        self._cascading = False

    # ------------------------------------------------------------------ #
    # Query
    # ------------------------------------------------------------------ #
    def get_checked_signals(self):
        result = []
        for (can_id, sig_name), item in self._signal_items.items():
            if item.checkState() == Qt.Checked:
                result.append((can_id, sig_name, item.data(self.SIGNAL_OBJ_ROLE)))
        return result
