"""Background thread for CAN polling loop."""

import time
from PyQt5.QtCore import QThread


class CanWorker(QThread):
    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def run(self):
        while not self._stop_flag and self._backend._running:
            time.sleep(0.1)
