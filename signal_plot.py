"""Matplotlib-based signal plotting widget embedded in PyQt5."""

from collections import defaultdict
import numpy as np
import matplotlib
matplotlib.use("Qt5Agg")
matplotlib.rcParams["font.family"] = "FiraCode Nerd Font"
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.backend_bases import MouseButton
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QWidget


class _ScrollZoomCanvas(FigureCanvasQTAgg):
    """Canvas with mouse-wheel zoom, left-drag pan, and axis-lock via click."""

    def __init__(self, fig, parent=None):
        super().__init__(fig)
        self.setParent(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self._pan_start = None
        self._axis_lock = None  # None, 'x', or 'y'
        self.mpl_connect("button_press_event", self._on_axis_click)

    def _detect_axis(self, mx, my):
        """Return 'x', 'y', or None based on whether (mx, my) in display coords is near an axis."""
        ax = self.figure.axes[0]
        bbox = ax.bbox
        in_xarea = bbox.x0 <= mx <= bbox.x1
        in_yarea = bbox.y0 <= my <= bbox.y1
        near_xaxis = in_xarea and (my < bbox.y0 or my > bbox.y1)
        near_yaxis = in_yarea and mx < bbox.x0
        if near_xaxis:
            return 'x'
        if near_yaxis:
            return 'y'
        return None

    def _on_axis_click(self, event):
        if event.button != MouseButton.LEFT:
            return
        if event.x is None or event.y is None:
            return
        hit = self._detect_axis(event.x, event.y)
        if hit is not None:
            self._pan_start = None
            self._axis_lock = hit if self._axis_lock != hit else None
            self._update_axis_highlight()
            self.draw()
        else:
            self._axis_lock = None
            self._update_axis_highlight()
            self.draw()

    def _update_axis_highlight(self):
        """Highlight the locked axis spine."""
        ax = self.figure.axes[0]
        for spine_name, spine in ax.spines.items():
            if spine_name in ('bottom', 'top') and self._axis_lock == 'x':
                spine.set_linewidth(2.5)
                spine.set_color("#4263eb")
            elif spine_name in ('left', 'right') and self._axis_lock == 'y':
                spine.set_linewidth(2.5)
                spine.set_color("#4263eb")
            else:
                spine.set_linewidth(1.0)
                spine.set_color("#dee2e6")

    def wheelEvent(self, event):
        ax = self.figure.axes[0]
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        scale = 0.9 if event.angleDelta().y() > 0 else 1.1
        inv = ax.transData.inverted()
        cx, cy = inv.transform((event.x(), event.y()))

        lock = self._axis_lock
        if lock is None:
            lock = self._detect_axis(event.x(), event.y())

        if lock == 'x':
            ax.set_xlim((cx - (cx - xlim[0]) * scale, cx + (xlim[1] - cx) * scale))
        elif lock == 'y':
            ax.set_ylim((cy - (cy - ylim[0]) * scale, cy + (ylim[1] - cy) * scale))
        else:
            ax.set_xlim((cx - (cx - xlim[0]) * scale, cx + (xlim[1] - cx) * scale))
            ax.set_ylim((cy - (cy - ylim[0]) * scale, cy + (ylim[1] - cy) * scale))
        self.draw()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pan_start = (event.x(), event.y())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_start is not None:
            ax = self.figure.axes[0]
            dx = event.x() - self._pan_start[0]
            dy = event.y() - self._pan_start[1]
            self._pan_start = (event.x(), event.y())
            inv = ax.transData.inverted()
            x0, y0 = inv.transform((0, 0))
            x1, y1 = inv.transform((dx, -dy))
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()
            ax.set_xlim(xlim[0] - (x1 - x0), xlim[1] - (x1 - x0))
            ax.set_ylim(ylim[0] - (y1 - y0), ylim[1] - (y1 - y0))
            self.draw()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._pan_start = None
        super().mouseReleaseEvent(event)


class SignalPlot(QWidget):
    """Signal plot with zoom, pan, and legend-click highlighting."""

    _COLORS = ["#00b4d8", "#ff6b35", "#2ecc71", "#e74c3c",
               "#9b59b6", "#f1c40f", "#1abc9c", "#e67e22",
               "#3498db", "#fd79a8"]
    _MAX_DISPLAY = 50000

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._fig = Figure(figsize=(8, 6), dpi=100, facecolor="#ffffff")
        self._canvas = _ScrollZoomCanvas(self._fig, self)
        self._toolbar = NavigationToolbar2QT(self._canvas, self)

        layout.addWidget(self._toolbar)
        layout.addWidget(self._canvas, 1)

        self._ax = self._fig.add_subplot(111)
        self._ax.set_facecolor("#fafbfc")
        self._ax.tick_params(colors="#868e96", labelsize=8)
        for spine in self._ax.spines.values():
            spine.set_color("#dee2e6")
        self._ax.set_xlabel("Time (s)", color="#495057")
        self._ax.set_ylabel("Value", color="#495057")
        self._ax.grid(True, alpha=0.5, color="#e9ecef")
        self._fig.set_tight_layout(True)

        self._lines = {}
        self._data = {}
        self._base_ts = None
        self._view_set = False
        self._picked_line = None
        self._canvas.mpl_connect("pick_event", self._on_pick)
        self._canvas.mpl_connect("button_press_event", self._on_click)

    def clear_data(self):
        for key in self._data:
            self._data[key] = ([], [])
        self._base_ts = None
        self._view_set = False
        self.update_plot()

    def set_signals(self, checked_signals):
        new_keys = {(can_id, sig_name) for can_id, sig_name, _ in checked_signals}

        for key in set(self._lines.keys()) - new_keys:
            self._lines[key].remove()
            del self._lines[key]
            del self._data[key]

        need_legend = False
        for i, (can_id, sig_name, _sig_obj) in enumerate(checked_signals):
            key = (can_id, sig_name)
            if key not in self._lines:
                color = self._COLORS[i % len(self._COLORS)]
                label = f"0x{can_id:03X}/{sig_name}"
                line, = self._ax.plot([], [], color=color, label=label, linewidth=1.2,
                                      picker=True, pickradius=5)
                self._lines[key] = line
                self._data[key] = ([], [])
                need_legend = True

        if not self._lines:
            self._base_ts = None
            self._view_set = False

        if need_legend or not hasattr(self, '_legend') or self._legend is None:
            if hasattr(self, '_legend') and self._legend:
                self._legend.remove()
            if self._lines:
                self._legend = self._ax.legend(loc="upper right", fontsize=9, ncol=2,
                                               facecolor="#ffffff", edgecolor="#e9ecef",
                                               labelcolor="#495057")
                for txt in self._legend.get_texts():
                    txt.set_picker(True)
            else:
                self._legend = None

        self._canvas.draw()

    def add_point(self, timestamp, can_id, sig_name, value):
        if self._base_ts is None:
            self._base_ts = timestamp
        key = (can_id, sig_name)
        if key not in self._data:
            return
        was_empty = not self._data[key][0]
        t = timestamp - self._base_ts
        v = float(value.value) if hasattr(value, 'value') else float(value)
        self._data[key][0].append(t)
        self._data[key][1].append(v)
        if was_empty:
            self._view_set = False

    def update_plot(self):
        for key, line in self._lines.items():
            ts, vs = self._data[key]
            if not ts:
                continue
            n = len(ts)
            if n > self._MAX_DISPLAY:
                stride = n // self._MAX_DISPLAY
                xs = np.array(ts[::stride])
                ys = np.array(vs[::stride])
            else:
                xs = np.array(ts)
                ys = np.array(vs)
            line.set_data(xs, ys)

        if self._lines:
            self._ax.relim()
            if not self._view_set:
                self._ax.autoscale_view()
                self._view_set = True
        self._canvas.draw()

    def _on_click(self, event):
        if event.inaxes is None or not hasattr(self, '_legend'):
            return
        leg = self._legend
        if not leg.get_draggable() and not leg.contains(event)[0]:
            return

        for txt in leg.get_texts():
            if txt.contains(event)[0]:
                for _key, line in self._lines.items():
                    if line.get_label() == txt.get_text():
                        self._highlight(line)
                        return

    def _highlight(self, line):
        if self._picked_line is line:
            self._reset_highlight()
            return
        self._reset_highlight()
        self._picked_line = line
        line.set_linewidth(3.5)
        line.set_zorder(100)
        for _key, l in self._lines.items():
            if l is not line:
                l.set_alpha(0.12)
                l.set_zorder(1)
        label = line.get_label()
        for txt in self._legend.get_texts():
            if txt.get_text() == label:
                txt.set_fontweight("bold")
                txt.set_color(line.get_color())
            else:
                txt.set_alpha(0.2)
        self._canvas.draw()

    def _on_pick(self, event):
        artist = event.artist
        if isinstance(artist, matplotlib.text.Text):
            for _key, line in self._lines.items():
                if line.get_label() == artist.get_text():
                    artist = line
                    break
        if not hasattr(artist, 'get_label'):
            return
        self._highlight(artist)

    def _reset_highlight(self):
        for _key, line in self._lines.items():
            line.set_alpha(1.0)
            line.set_linewidth(1.2)
            line.set_zorder(2)
        self._picked_line = None
        if hasattr(self, '_legend') and self._legend:
            for txt in self._legend.get_texts():
                txt.set_fontweight("normal")
                txt.set_alpha(1.0)
                txt.set_color("#495057")
