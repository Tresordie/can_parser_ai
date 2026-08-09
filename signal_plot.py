"""Matplotlib-based signal plotting widget embedded in PyQt5.

Performance model
-----------------
- Each signal keeps its samples as two numpy arrays ``(t, v)`` so bulk loads
  from a pre-parsed log are O(1) assignments instead of per-point appends
  (see :meth:`set_series`). Live samples land in small Python list buffers
  first and are concatenated into the arrays once per frame, so streaming
  ingestion is amortised O(1) instead of an O(n^2) ``np.append`` per point.
- Rendering uses matplotlib *blitting*: lines and the hover overlay are
  ``animated`` artists. Every full draw (zoom/pan/highlight/resize) ends in
  a ``draw_event`` that captures a clean background (animated artists are
  excluded); subsequent frames just restore it and re-rasterise the lines.
- Autoscale bounds are computed from the data arrays only when the view is
  reset — never via a per-frame ``relim()`` scan.
- Downsampling is view-aware min-max decimation: within the visible x-range
  each block keeps its argmin/argmax sample, so spikes and step edges stay
  faithful and we never draw more than ``_MAX_DISPLAY`` points per line.
"""

from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use("Qt5Agg")

# ── Dark-theme defaults for all matplotlib elements ──
matplotlib.rcParams.update({
    "font.family":         "Segoe UI",
    "font.size":            9,
    "figure.facecolor":     "#0d1117",
    "axes.facecolor":       "#0d1117",
    "axes.edgecolor":       "#30363d",
    "axes.labelcolor":      "#8b949e",
    "axes.grid":            True,
    "grid.color":           "#21262d",
    "grid.alpha":           0.8,
    "xtick.color":          "#8b949e",
    "ytick.color":          "#8b949e",
    "text.color":           "#e6edf3",
    "legend.facecolor":     "#161b22",
    "legend.edgecolor":     "#30363d",
})

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT as _NavToolbarBase
from matplotlib.figure import Figure
from matplotlib.backend_bases import MouseButton
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QSizePolicy, QVBoxLayout, QWidget


class _DarkNavToolbar(_NavToolbarBase):
    """Navigation toolbar styled for the dark theme."""

    def __init__(self, canvas, parent):
        super().__init__(canvas, parent)
        self.setStyleSheet("""
            QToolBar {
                background-color: #161b22; border: none;
                spacing: 2px; padding: 2px;
            }
            QToolButton {
                background-color: transparent; color: #8b949e;
                border: 1px solid transparent; border-radius: 4px;
                padding: 4px 6px; font-size: 11px; min-width: 24px;
            }
            QToolButton:hover {
                background-color: #21262d; color: #e6edf3;
                border-color: #30363d;
            }
            QToolButton:pressed { background-color: #30363d; }
        """)

    def save_figure(self, *args):
        """Un-animate artists around savefig — animated artists are skipped
        by the normal draw, so the saved image would miss every curve."""
        animated = [
            a for ax in self.canvas.figure.axes
            for a in ax.get_children() if a.get_animated()
        ]
        for a in animated:
            a.set_animated(False)
        try:
            super().save_figure(*args)
        finally:
            for a in animated:
                a.set_animated(True)


class _ScrollZoomCanvas(FigureCanvasQTAgg):
    """Canvas with mouse-wheel zoom, left-drag pan, and axis-lock via click."""

    def __init__(self, fig, parent=None):
        super().__init__(fig)
        self.setParent(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._pan_start = None
        self._axis_lock = None  # None, 'x', or 'y'
        self._on_resize_cb = None
        self._interact_cb = None  # notify host on pan/zoom/axis-lock
        self.mpl_connect("button_press_event", self._on_axis_click)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._on_resize_cb:
            self._on_resize_cb()

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

    def _notify_interact(self):
        if self._interact_cb:
            self._interact_cb()

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
            self.draw_idle()
            self._notify_interact()
        else:
            self._axis_lock = None
            self._update_axis_highlight()
            self.draw_idle()
            self._notify_interact()

    def _update_axis_highlight(self):
        """Highlight the locked axis spine."""
        ax = self.figure.axes[0]
        for spine_name, spine in ax.spines.items():
            if spine_name in ('bottom', 'top') and self._axis_lock == 'x':
                spine.set_linewidth(2.5)
                spine.set_color("#58a6ff")
            elif spine_name in ('left', 'right') and self._axis_lock == 'y':
                spine.set_linewidth(2.5)
                spine.set_color("#58a6ff")
            else:
                spine.set_linewidth(1.0)
                spine.set_color("#30363d")

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
        # draw_idle (not draw): Qt coalesces bursts of wheel ticks into one
        # paint, and the resulting draw_event refreshes the blit background.
        self.draw_idle()
        self._notify_interact()

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
            # draw_idle so a fast drag coalesces into fewer full paints.
            self.draw_idle()
            self._notify_interact()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._pan_start = None
        super().mouseReleaseEvent(event)


class SignalPlot(QWidget):
    """Signal plot with zoom, pan, and legend-click highlighting."""

    # Emitted when the user clicks a legend label. Carries (can_id, sig_name)
    # so the host can select the corresponding signal in the tree.
    signal_label_clicked = pyqtSignal(int, str)

    _COLORS = ["#58a6ff", "#3fb950", "#f0883e", "#f778ba",
               "#bc8cff", "#d2a8ff", "#79c0ff", "#56d364",
               "#e3b341", "#ff7b72"]
    # Soft cap on points drawn per line. Above this the view becomes
    # pixel-saturated anyway, so we decimate to keep every frame ~tens of ms.
    _MAX_DISPLAY = 10000

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._fig = Figure(figsize=(8, 6), dpi=100,
                           facecolor="#0d1117", constrained_layout=True)
        self._canvas = _ScrollZoomCanvas(self._fig, self)
        self._canvas._on_resize_cb = self._on_canvas_resize
        self._canvas._interact_cb = self._invalidate_blit
        self._toolbar = _DarkNavToolbar(self._canvas, self)

        layout.addWidget(self._toolbar)
        layout.addWidget(self._canvas, 1)

        self._ax = self._fig.add_subplot(111)
        self._ax.set_facecolor("#0d1117")
        self._ax.tick_params(colors="#8b949e", labelsize=8)
        for spine in self._ax.spines.values():
            spine.set_color("#30363d")
            spine.set_linewidth(1.0)
        self._ax.set_xlabel("Time (s)", color="#8b949e", fontsize=10)
        self._ax.set_ylabel("Value", color="#8b949e", fontsize=10)
        self._ax.grid(True, alpha=0.4, color="#21262d")

        self._lines = {}        # key: (can_id, sig_name, instance_id) -> line
        # key: (can_id, sig_name) -> entry dict, see _new_entry()
        self._data = {}
        self._next_inst = {}    # key: (can_id, sig_name) -> next instance id
        self._sig_active = set()  # (can_id, sig_name) pairs with active lines
        self._dirty = False       # True if new data added since last draw
        self._base_ts = None
        self._view_set = False
        self._picked_line = None
        self._legend = None
        self._legend_fontsize = 8

        # Blitting state. The background is (re)captured automatically in
        # _on_draw after every full paint — nothing has to prime it.
        self._blit_enabled = False
        self._background = None
        # Set whenever the view changes so the next render re-downsamples.
        self._view_changed = True
        self._invalidate_blit()

        # Hover crosshair + tooltip
        self._crosshair = self._ax.axvline(
            0, color="#8b949e", linewidth=0.8, linestyle="--",
            visible=False, animated=True,
        )
        self._tip = self._ax.text(
            0, 0, "", fontsize=8, color="#e6edf3",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#161b22",
                      edgecolor="#30363d", alpha=0.92),
            visible=False, animated=True, zorder=200,
        )

        self._canvas.mpl_connect("pick_event", self._on_pick)
        self._canvas.mpl_connect("button_press_event", self._on_click)
        self._canvas.mpl_connect("draw_event", self._on_draw)
        self._canvas.mpl_connect("motion_notify_event", self._on_hover)

    # ------------------------------------------------------------------ #
    # Blitting helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _new_entry():
        """Fresh per-signal data slot.

        ``t``/``v`` hold the committed numpy arrays; ``pt``/``pv`` are small
        Python list buffers fed by :meth:`add_point` and concatenated into
        the arrays once per frame (amortised O(1) ingestion).
        """
        return {"t": np.empty(0), "v": np.empty(0),
                "pt": [], "pv": [], "dirty": True}

    def _invalidate_blit(self):
        """Mark the cached background stale; the next full draw (triggered by
        the caller via ``draw_idle``) re-captures it in ``_on_draw``.

        Also flags a view change so per-line data is re-downsampled against
        the new x-range after a pan/zoom/axis-lock.
        """
        self._blit_enabled = False
        self._background = None
        self._view_changed = True
        self._dirty = True

    def _blit_animated(self):
        """Restore the cached background and redraw animated artists only.

        Returns True on success; False when no background is available and
        the caller should fall back to ``draw_idle``.
        """
        if not self._blit_enabled or self._background is None:
            return False
        ax = self._ax
        self._canvas.restore_region(self._background)
        for line in self._lines.values():
            ax.draw_artist(line)
        if self._crosshair.get_visible():
            ax.draw_artist(self._crosshair)
        if self._tip.get_visible():
            ax.draw_artist(self._tip)
        self._canvas.blit(ax.bbox)
        return True

    def _on_canvas_resize(self):
        """Called after the canvas has been resized by Qt layout."""
        self._invalidate_blit()
        if self._legend is not None:
            self._rebuild_legend()
            self._canvas.draw_idle()

    # ------------------------------------------------------------------ #
    # Signal lifecycle
    # ------------------------------------------------------------------ #
    def clear_data(self):
        for line in self._lines.values():
            line.remove()
        for key in self._data:
            self._data[key] = self._new_entry()
        self._lines.clear()
        self._next_inst.clear()
        self._sig_active.clear()
        self._base_ts = None
        self._view_set = False
        self._dirty = True
        self._rebuild_legend()
        self.update_plot()
        self._invalidate_blit()

    def set_signals(self, checked_signals):
        new_sigs = {(can_id, sig_name) for can_id, sig_name, _ in checked_signals}

        # Remove lines and data for unchecked signals
        removed_sigs = set()
        for key in list(self._lines.keys()):
            sig_key = (key[0], key[1])
            if sig_key not in new_sigs:
                self._lines[key].remove()
                del self._lines[key]
                removed_sigs.add(sig_key)

        for sig_key in list(self._data.keys()):
            if sig_key not in new_sigs:
                del self._data[sig_key]
                self._next_inst.pop(sig_key, None)

        self._sig_active.difference_update(removed_sigs)
        self._sig_active.intersection_update(new_sigs)

        need_legend = bool(removed_sigs)
        for i, (can_id, sig_name, _sig_obj) in enumerate(checked_signals):
            sig_key = (can_id, sig_name)
            if sig_key not in self._data:
                self._data[sig_key] = self._new_entry()

            if sig_key not in self._sig_active:
                inst = self._next_inst.get(sig_key, 0)
                self._next_inst[sig_key] = inst + 1
                line_key = (can_id, sig_name, inst)
                ci = len(self._lines)
                color = self._COLORS[ci % len(self._COLORS)]
                label = f"0x{can_id:03X}/{sig_name}"
                if inst > 0:
                    label += f" [{inst}]"
                # animated=True: excluded from the cached background and
                # redrawn via blit every frame (see _blit_animated).
                line, = self._ax.plot([], [], color=color, label=label, linewidth=1.2,
                                      picker=True, pickradius=5, animated=True)
                self._lines[line_key] = line
                self._sig_active.add(sig_key)
                need_legend = True

        if not self._data:
            self._base_ts = None
            self._view_set = False

        self._dirty = True
        if need_legend or self._legend is None:
            self._rebuild_legend()

        self._invalidate_blit()
        self._canvas.draw_idle()

    def set_legend_fontsize(self, size):
        self._legend_fontsize = size
        if self._lines:
            self._rebuild_legend()
            self._invalidate_blit()
            self._canvas.draw_idle()

    def _rebuild_legend(self):
        if self._legend:
            self._legend.remove()
        if not self._lines:
            self._legend = None
            return
        n = len(self._lines)
        if n <= 3:
            ncol = 1
        elif n <= 6:
            ncol = 2
        elif n <= 10:
            ncol = 3
        elif n <= 16:
            ncol = 4
        elif n <= 24:
            ncol = 5
        elif n <= 34:
            ncol = 6
        else:
            ncol = 7
        self._legend = self._ax.legend(
            loc="upper right", fontsize=self._legend_fontsize, ncol=ncol,
            facecolor="#161b22", edgecolor="#30363d",
            labelcolor="#e6edf3")
        self._legend.set_in_layout(False)
        for txt in self._legend.get_texts():
            txt.set_picker(True)

    def add_signal_instance(self, can_id, sig_name):
        """Add a duplicate instance of an already-active signal."""
        sig_key = (can_id, sig_name)
        if sig_key not in self._data:
            return
        inst = self._next_inst.get(sig_key, 0)
        self._next_inst[sig_key] = inst + 1
        line_key = (can_id, sig_name, inst)
        ci = len(self._lines)
        color = self._COLORS[ci % len(self._COLORS)]
        label = f"0x{can_id:03X}/{sig_name} [{inst}]"
        line, = self._ax.plot([], [], color=color, label=label, linewidth=1.2,
                              picker=True, pickradius=5, animated=True)
        self._lines[line_key] = line
        self._rebuild_legend()
        self._invalidate_blit()
        self._canvas.draw_idle()

    def highlight_signal(self, can_id, sig_name):
        """Highlight the line for ``(can_id, sig_name)`` from outside the plot.

        Called when the user checks a signal in the tree so the plot, legend
        and tree all stay in sync. If the signal is not currently plotted or
        is already highlighted, this is a no-op.
        """
        # Find the (first) line matching this can_id/sig_name.
        for (lc_id, ls_name, _inst), line in self._lines.items():
            if lc_id == can_id and ls_name == sig_name:
                if self._picked_line is not line:
                    self._highlight(line)
                return

    def clear_highlight(self):
        """Remove any highlight (e.g. when the signal is unchecked)."""
        if self._picked_line is not None:
            self._reset_highlight()
            self._invalidate_blit()
            self._canvas.draw()

    # ------------------------------------------------------------------ #
    # Data ingestion
    # ------------------------------------------------------------------ #
    def set_series(self, can_id, sig_name, t_array, v_array):
        """Bulk-load a pre-decoded signal series (O(1) after assignment).

        Used when adding a signal whose data is already fully decoded in the
        backend index (log playback / newly checked signal).
        """
        sig_key = (can_id, sig_name)
        entry = self._data.get(sig_key)
        if entry is None:
            return
        t = np.asarray(t_array, dtype=np.float64)
        v = np.asarray(v_array, dtype=np.float64)
        if self._base_ts is None and t.size:
            self._base_ts = float(t[0])
        if t.size and self._base_ts is not None:
            t = t - self._base_ts
        entry["t"] = t
        entry["v"] = v
        entry["pt"].clear()
        entry["pv"].clear()
        entry["dirty"] = True
        self._dirty = True
        self._view_set = False

    def add_point(self, timestamp, can_id, sig_name, value):
        """Append a single sample (live capture / streaming replay).

        Samples land in a Python list buffer; :meth:`update_plot` flushes it
        into the numpy arrays once per frame — one concatenation per signal
        per frame instead of a full-array copy per point.
        """
        if self._base_ts is None:
            self._base_ts = timestamp
        key = (can_id, sig_name)
        entry = self._data.get(key)
        if entry is None:
            return
        if entry["t"].size == 0 and not entry["pt"]:
            self._view_set = False
        entry["pt"].append(timestamp - self._base_ts)
        entry["pv"].append(float(value.value) if hasattr(value, 'value') else float(value))
        entry["dirty"] = True
        self._dirty = True

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #
    def update_plot(self):
        if not self._dirty:
            return
        self._dirty = False
        # view_changed forces every line to re-decimate against the new xlim.
        force_resample = self._view_changed
        self._view_changed = False

        ax = self._ax
        any_data = False
        for key, line in self._lines.items():
            sig_key = (key[0], key[1])
            entry = self._data.get(sig_key)
            if entry is None:
                continue
            # Flush pending live samples into the numpy arrays (one concat per
            # signal per frame — amortised O(1) ingestion).
            if entry["pt"]:
                entry["t"] = np.concatenate(
                    [entry["t"], np.asarray(entry["pt"], dtype=np.float64)])
                entry["v"] = np.concatenate(
                    [entry["v"], np.asarray(entry["pv"], dtype=np.float64)])
                entry["pt"].clear()
                entry["pv"].clear()
                entry["dirty"] = True
            t = entry["t"]
            v = entry["v"]
            if t.size == 0:
                line.set_data(t, v)
                continue
            any_data = True
            # Skip recomputation when neither data nor the view moved.
            if not force_resample and not entry.get("dirty"):
                continue
            entry["dirty"] = False
            xs, ys = self._downsample(t, v)
            line.set_data(xs, ys)

        # Autoscale only when the view resets (first data / new series).
        # Bounds come straight from the arrays — no per-frame relim() scan.
        if any_data and not self._view_set:
            self._autoscale_all()
            self._view_set = True

        # Blit if we can, otherwise a normal idle redraw (which ends in
        # _on_draw and refreshes the blit background for next time).
        if not self._blit_animated():
            self._canvas.draw_idle()

    def _autoscale_all(self):
        """Set the view to cover every loaded series (matplotlib-style 5%
        margins). Called only on view resets, never per frame."""
        xmin = ymin = np.inf
        xmax = ymax = -np.inf
        for entry in self._data.values():
            t = entry["t"]
            if t.size == 0:
                continue
            xmin = min(xmin, float(t[0]))
            xmax = max(xmax, float(t[-1]))
            v = entry["v"]
            vmin = float(np.nanmin(v))
            vmax = float(np.nanmax(v))
            ymin = min(ymin, vmin)
            ymax = max(ymax, vmax)
        if not np.isfinite(xmin):
            return
        xpad = (xmax - xmin) * 0.05 or 0.5
        yspan = ymax - ymin
        if yspan <= 0:
            yspan = max(1.0, abs(ymax) * 0.1)
        ypad = yspan * 0.05
        self._ax.set_xlim(xmin - xpad, xmax + xpad)
        self._ax.set_ylim(ymin - ypad, ymax + ypad)

    def _downsample(self, t, v):
        """View-aware min-max decimation within the visible x-range.

        Each block keeps its argmin and argmax sample, so spikes and step
        edges survive decimation (plain stride decimation would drop them).
        Never returns more than ``_MAX_DISPLAY`` points.
        """
        n = t.size
        if n <= self._MAX_DISPLAY:
            return t, v
        lo, hi = self._ax.get_xlim()
        # Find the index window covering [lo, hi] via sorted-array search.
        i0 = int(np.searchsorted(t, lo, side="left"))
        i1 = int(np.searchsorted(t, hi, side="right"))
        # Add a margin so panning does not pop in/out at the edges.
        margin = self._MAX_DISPLAY // 2
        start = max(0, i0 - margin)
        stop = min(n, i1 + margin)
        seg = stop - start
        if seg <= self._MAX_DISPLAY:
            return t[start:stop], v[start:stop]
        # Vectorised per-block argmin/argmax over the value window.
        nblocks = self._MAX_DISPLAY // 2
        block = seg // nblocks
        usable = block * nblocks
        vs_win = v[start:start + usable].reshape(nblocks, block)
        offsets = start + np.arange(nblocks) * block
        idx = np.unique(np.concatenate([
            offsets + vs_win.argmin(axis=1),
            offsets + vs_win.argmax(axis=1),
        ]))
        # Anchor the very last point so the line reaches the right edge.
        if idx[-1] != stop - 1:
            idx = np.append(idx, stop - 1)
        return t[idx], v[idx]

    def _on_hover(self, event):
        """Show crosshair + tooltip near the nearest data point on hover.

        The overlay artists are animated, so each move is a cheap blit
        against the cached background instead of a full redraw.
        """
        if event.inaxes is None or not self._data:
            self._crosshair.set_visible(False)
            self._tip.set_visible(False)
            if not self._blit_animated():
                self._canvas.draw_idle()
            return

        mx = event.xdata
        if mx is None:
            return

        # Find the closest (t, v) across all loaded signals via binary search.
        best_key = None
        best_idx = 0
        best_dist = float("inf")
        for sig_key, entry in self._data.items():
            t = entry["t"]
            if t.size == 0:
                continue
            idx = int(np.searchsorted(t, mx))
            if idx >= len(t):
                idx = len(t) - 1
            elif idx > 0 and abs(t[idx - 1] - mx) < abs(t[idx] - mx):
                idx -= 1
            d = abs(t[idx] - mx)
            if d < best_dist:
                best_dist = d
                best_key = sig_key
                best_idx = idx

        if best_key is None:
            self._crosshair.set_visible(False)
            self._tip.set_visible(False)
            if not self._blit_animated():
                self._canvas.draw_idle()
            return

        can_id, sig_name = best_key
        entry = self._data[best_key]
        tx = float(entry["t"][best_idx])
        tv = float(entry["v"][best_idx])

        self._crosshair.set_xdata([tx, tx])
        self._crosshair.set_visible(True)

        label = f"0x{can_id:03X}/{sig_name}\nt = {tx:.6f} s\nv = {tv:.6g}"
        self._tip.set_text(label)
        # Place the tooltip near the data point, clamped to the visible y-range.
        y_lo, y_hi = self._ax.get_ylim()
        ty = max(y_lo, min(y_hi, tv))
        self._tip.set_position((tx, ty))
        self._tip.set_visible(True)

        if not self._blit_animated():
            self._canvas.draw_idle()

    def _on_click(self, event):
        # Check the legend first — it may overlap the axes or sit outside it,
        # so we cannot rely on event.inaxes to decide whether the click hit a
        # legend entry.
        self._sync_legend()
        if self._legend is not None:
            leg = self._legend
            if leg.contains(event)[0]:
                for txt in leg.get_texts():
                    if txt.contains(event)[0]:
                        label = txt.get_text()
                        for _key, line in self._lines.items():
                            if line.get_label() == label:
                                self._highlight(line)
                                self._emit_label_clicked(label)
                                return
        # Click in the plot area — if it hit a data line, highlight it
        # and emit the label-clicked signal so the tree selects it too.
        if event.inaxes is not None:
            for line in self._lines.values():
                if line.contains(event)[0]:
                    self._highlight(line)
                    self._emit_label_clicked(line.get_label())
                    return
            # Click on empty area inside axes — exit highlighting.
            self._reset_highlight()
            self._canvas.draw()

    def _emit_label_clicked(self, label):
        """Parse a legend label "0xID/SigName [inst]" and emit the signal."""
        try:
            # Strip optional instance suffix " [n]"
            core = label.split(" [")[0]
            id_str, sig_name = core.split("/", 1)
            can_id = int(id_str, 16)
            self.signal_label_clicked.emit(can_id, sig_name)
        except (ValueError, IndexError):
            pass

    def _highlight(self, line):
        # Do NOT toggle: if the same line is already highlighted, keep it
        # highlighted. This prevents _on_click + _on_pick (both fire on a
        # single physical click) from cancelling each other's highlight.
        if self._picked_line is line:
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
        self._sync_legend()
        if self._legend is not None:
            for txt in self._legend.get_texts():
                if txt.get_text() == label:
                    txt.set_fontweight("bold")
                    txt.set_color(line.get_color())
                else:
                    txt.set_alpha(0.2)
        # Legend/spine changes can't be blitted; do a full draw.
        self._invalidate_blit()
        self._canvas.draw()

    def _on_pick(self, event):
        artist = event.artist
        if isinstance(artist, matplotlib.text.Text):
            for _key, line in self._lines.items():
                if line.get_label() == artist.get_text():
                    # Already highlighted by _on_click — don't double-emit.
                    if self._picked_line is line:
                        return
                    artist = line
                    break
        if not hasattr(artist, 'get_label'):
            return
        # Don't re-emit if _on_click already handled this click.
        if self._picked_line is artist:
            return
        self._highlight(artist)
        self._emit_label_clicked(artist.get_label())

    def _sync_legend(self):
        """Sync ``self._legend`` with the current legend on the axes so text
        modifications target the visible legend, not a stale one that may
        have been removed by a prior ``_rebuild_legend`` call."""
        leg = self._ax.get_legend()
        if leg is not None:
            self._legend = leg

    def _reset_highlight(self):
        for _key, line in self._lines.items():
            line.set_alpha(1.0)
            line.set_linewidth(1.2)
            line.set_zorder(2)
        self._picked_line = None
        self._sync_legend()
        if self._legend is not None:
            for txt in self._legend.get_texts():
                txt.set_fontweight("normal")
                txt.set_alpha(1.0)
                txt.set_color("#e6edf3")
        self._invalidate_blit()

    def _on_draw(self, event):
        """After every full paint: keep the legend as overlay (not affecting
        axes layout), then capture a clean background for blitting — animated
        artists (lines, crosshair, tooltip) were excluded from this paint —
        and redraw them on top so nothing disappears."""
        leg = self._ax.get_legend()
        if leg is not None and leg.get_in_layout():
            leg.set_in_layout(False)
        # keep our reference in sync
        if leg is not None and leg is not self._legend:
            self._legend = leg

        self._background = self._canvas.copy_from_bbox(self._ax.bbox)
        self._blit_enabled = True
        ax = self._ax
        for line in self._lines.values():
            ax.draw_artist(line)
        if self._crosshair.get_visible():
            ax.draw_artist(self._crosshair)
        if self._tip.get_visible():
            ax.draw_artist(self._tip)
        self._canvas.blit(ax.bbox)
