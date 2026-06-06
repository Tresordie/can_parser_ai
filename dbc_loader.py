"""DBC file loading and signal tree model — signals default unchecked."""

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

                for sig in msg.signals:
                    sig_item = QStandardItem(sig.name)
                    sig_item.setFlags(sig_item.flags() | Qt.ItemIsUserCheckable)
                    sig_item.setCheckState(Qt.Unchecked)
                    sig_item.setData(self.ITEM_TYPE_SIGNAL, self.CHECKED_ROLE)
                    sig_item.setData(msg.frame_id, self.CAN_ID_ROLE)
                    sig_item.setData(sig, self.SIGNAL_OBJ_ROLE)
                    msg_item.appendRow(sig_item)
                    key = (msg.frame_id, sig.name)
                    self._signal_items[key] = sig_item

            self.dbc_loaded.emit(self._db)
            return True
        except Exception as e:
            self._model.clear()
            self.error_occurred.emit(f"Failed to load DBC: {e}")
            return False

    def cascade_check_state(self, item):
        if self._cascading:
            return
        self._cascading = True
        item_type = item.data(self.CHECKED_ROLE)
        state = item.checkState()

        if item_type == self.ITEM_TYPE_MESSAGE:
            for row in range(item.rowCount()):
                item.child(row).setCheckState(state)

        elif item_type == self.ITEM_TYPE_SIGNAL:
            parent = item.parent()
            if parent:
                all_checked = all(
                    parent.child(r).checkState() == Qt.Checked
                    for r in range(parent.rowCount())
                )
                all_unchecked = all(
                    parent.child(r).checkState() == Qt.Unchecked
                    for r in range(parent.rowCount())
                )
                if all_checked:
                    parent.setCheckState(Qt.Checked)
                elif all_unchecked:
                    parent.setCheckState(Qt.Unchecked)
                else:
                    parent.setCheckState(Qt.PartiallyChecked)

        self._cascading = False

    def select_all(self):
        self._cascading = True
        for _can_id, msg_item in self._message_items.items():
            msg_item.setCheckState(Qt.Checked)
            for row in range(msg_item.rowCount()):
                msg_item.child(row).setCheckState(Qt.Checked)
        self._cascading = False

    def deselect_all(self):
        self._cascading = True
        for _can_id, msg_item in self._message_items.items():
            msg_item.setCheckState(Qt.Unchecked)
            for row in range(msg_item.rowCount()):
                msg_item.child(row).setCheckState(Qt.Unchecked)
        self._cascading = False

    def get_checked_signals(self):
        result = []
        for (can_id, sig_name), item in self._signal_items.items():
            if item.checkState() == Qt.Checked:
                result.append((can_id, sig_name, item.data(self.SIGNAL_OBJ_ROLE)))
        return result
