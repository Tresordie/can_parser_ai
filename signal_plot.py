"""Matplotlib-based signal plotting widget embedded in PyQt5.

Performance model
-----------------
- Each signal keeps its samples as two numpy arrays ``(t, v)`` so bulk loads
  from a pre-parsed log are O(1) assignments instead of per-point appends
  (see :meth:`set_series`).
- Rendering uses matplotlib *blitting*: only the changed line artists are
  redrawn against a cached background each frame. Any interaction that can
  move axes (zoom/pan/axis-lock/legend-click/resize) invalidates the cache
  and forces one full draw before blitting resumes.
- Downsampling is view-aware: when the visible x-range exceeds
  ``_MAX_DISPLAY`` points we stride within that range, not the whole series.
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
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
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
    # The legend re-measures every entry on each full draw (~150 ms for 24
    # signals — the dominant cost of a zoom/pan frame). While wheel/pan
    # events keep arriving it stays hidden and is restored once the burst
    # settles. Below this many entries the saving isn't worth the flicker.
    _LEGEND_HIDE_MIN = 8
    _LEGEND_RESTORE_MS = 180

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._fig = Figure(figsize=(8, 6), dpi=100,
                           facecolor="#0d1117", constrained_layout=True)
        self._canvas = _ScrollZoomCanvas(self._fig, self)
        self._canvas._on_resize_cb = self._on_canvas_resize
        self._canvas._interact_cb = self._on_view_interact

        self._legend_idle_timer = QTimer(self)
        self._legend_idle_timer.setSingleShot(True)
        self._legend_idle_timer.setInterval(self._LEGEND_RESTORE_MS)
        self._legend_idle_timer.timeout.connect(self._restore_legend)
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
        # key: (can_id, sig_name) -> {"t": np.ndarray, "v": np.ndarray, "dirty": bool}
        self._data = {}
        self._next_inst = {}    # key: (can_id, sig_name) -> next instance id
        self._sig_active = set()  # (can_id, sig_name) pairs with active lines
        self._dirty = False       # True if new data added since last draw
        self._base_ts = None
        self._view_set = False
        self._picked_line = None
        self._legend = None
        self._legend_fontsize = 8
        # Display-only moving-average filter (see set_smoothing).
        self._smooth_enabled = False
        self._smooth_window = 9

        # Blitting state.
        self._blit_enabled = False
        self._background = None
        # Set whenever the view changes so the next render re-downsamples.
        self._view_changed = True
        # Force the first frame to capture a fresh background.
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
    def _invalidate_blit(self):
        """Mark the cached background stale; next update_plot re-captures it.

        Also flags a view change so per-line data is re-downsampled against
        the new x-range after a pan/zoom/axis-lock.
        """
        self._blit_enabled = False
        self._background = None
        self._view_changed = True
        self._dirty = True

    def _on_view_interact(self):
        """Canvas callback for wheel-zoom / drag-pan / axis-lock clicks.

        Re-decimates the lines against the new view immediately (instead of
        waiting for the 250 ms refresh timer, which would draw stale data)
        and lets ``update_plot`` schedule a coalesced ``draw_idle`` — one
        full render per event-loop round, not one per queued event.
        """
        self._invalidate_blit()
        if self._legend is not None and len(self._lines) >= self._LEGEND_HIDE_MIN:
            if self._legend.get_visible():
                self._legend.set_visible(False)
            self._legend_idle_timer.start()
        self.update_plot()

    def _restore_legend(self):
        if self._legend is not None and not self._legend.get_visible():
            self._legend.set_visible(True)
            self._invalidate_blit()
            self._canvas.draw_idle()

    def _capture_background(self):
        """Cache the just-rendered static scene as the blit background.

        Called from ``_on_draw`` (draw_event) — at that moment the renderer
        buffer holds the full render, so the copy is exact and cheap. The
        animated artists (crosshair, tooltip) are skipped by the normal
        render, so they are never part of the background.
        """
        self._background = self._canvas.copy_from_bbox(self._ax.bbox)
        self._blit_enabled = True

    def _blit_overlay(self):
        """Redraw only the animated overlay (crosshair/tooltip) on top of the
        cached background — a few ms instead of a full canvas re-render."""
        if not self._blit_enabled or self._background is None:
            self._canvas.draw_idle()
            return
        self._canvas.restore_region(self._background)
        if self._crosshair.get_visible():
            self._ax.draw_artist(self._crosshair)
        if self._tip.get_visible():
            self._ax.draw_artist(self._tip)
        self._canvas.blit(self._ax.bbox)

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
                line, = self._ax.plot([], [], color=color, label=label, linewidth=1.2,
                                      picker=True, pickradius=5)
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

    def set_smoothing(self, enabled, window):
        """Toggle the display-only centered moving-average filter.

        Purely a view filter: raw series, the data table and CSV exports are
        never touched. The tooltip snaps to the smoothed curve while the
        filter is on.
        """
        window = max(1, int(window))
        if enabled == self._smooth_enabled and window == self._smooth_window:
            return
        self._smooth_enabled = enabled
        self._smooth_window = window
        for entry in self._data.values():
            entry["dirty"] = True
        self._dirty = True
        self.update_plot()

    @staticmethod
    def _moving_average(v, window):
        """Centered moving average with partial windows at both edges —
        O(n), no phase shift, no amplitude shrink at the ends."""
        n = v.size
        if window <= 1 or n == 0:
            return v
        half = max(1, window // 2)
        c = np.concatenate(([0.0], np.cumsum(v, dtype=np.float64)))
        idx = np.arange(n)
        lo = np.clip(idx - half, 0, n)
        hi = np.clip(idx + half + 1, 0, n)
        return (c[hi] - c[lo]) / (hi - lo)

    def _display_v(self, entry):
        """The value array currently drawn (smoothed when the filter is on
        and its cached result matches the current series)."""
        if self._smooth_enabled and self._smooth_window > 1:
            vs = entry.get("v_smooth")
            if vs is not None and vs.size == entry["t"].size:
                return vs
        return entry["v"]

    def _smoothed(self, entry):
        vs = entry.get("v_smooth")
        if (vs is None or entry.get("v_smooth_win") != self._smooth_window
                or vs.size != entry["t"].size):
            vs = self._moving_average(entry["v"], self._smooth_window)
            entry["v_smooth"] = vs
            entry["v_smooth_win"] = self._smooth_window
        return vs

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
        # Legend handles snapshot the line properties at build time. If the
        # legend is rebuilt while a highlight is active, the dimmed alpha
        # (0.12) of the other lines would be baked into their handles and the
        # legend would show no color even after the highlight is cleared.
        # Handles therefore always keep full opacity; the selection state is
        # carried by the text styling below.
        for h in self._legend.get_lines():
            h.set_alpha(1.0)
        if self._picked_line is not None:
            label = self._picked_line.get_label()
            for txt in self._legend.get_texts():
                if txt.get_text() == label:
                    txt.set_fontweight("bold")
                    txt.set_color(self._picked_line.get_color())
                else:
                    txt.set_alpha(0.2)

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
                              picker=True, pickradius=5)
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
    @staticmethod
    def _new_entry():
        # t_buf/v_buf hold live-capture points as plain Python lists between
        # update_plot ticks — see add_point.
        return {"t": np.empty(0), "v": np.empty(0), "dirty": True,
                "t_buf": [], "v_buf": []}

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
        # A bulk load supersedes any buffered points and any cached smoothing.
        entry["t_buf"].clear()
        entry["v_buf"].clear()
        entry.pop("v_smooth", None)
        entry["dirty"] = True
        self._dirty = True
        self._view_set = False

    def add_point(self, timestamp, can_id, sig_name, value):
        """Append a single sample (live capture).

        The point lands in a Python-list buffer that update_plot merges into
        the numpy series in one shot. Appending to the arrays directly is
        O(n) per point (np.append copies the whole array), which measured
        ~380x slower than this buffered path and degraded the UI after a few
        minutes of live capture.
        """
        if self._base_ts is None:
            self._base_ts = timestamp
        key = (can_id, sig_name)
        entry = self._data.get(key)
        if entry is None:
            return
        if entry["t"].size == 0 and not entry["t_buf"]:
            self._view_set = False
        t = timestamp - self._base_ts
        v = float(value.value) if hasattr(value, 'value') else float(value)
        entry["t_buf"].append(t)
        entry["v_buf"].append(v)
        entry["dirty"] = True
        self._dirty = True

    def _drain_buffers(self):
        """Merge buffered live points into the numpy series (batch append)."""
        for entry in self._data.values():
            if not entry["t_buf"]:
                continue
            t_new = np.asarray(entry["t_buf"], dtype=np.float64)
            v_new = np.asarray(entry["v_buf"], dtype=np.float64)
            entry["t_buf"].clear()
            entry["v_buf"].clear()
            if entry["t"].size == 0:
                entry["t"] = t_new
                entry["v"] = v_new
            else:
                entry["t"] = np.concatenate((entry["t"], t_new))
                entry["v"] = np.concatenate((entry["v"], v_new))
            entry["dirty"] = True
            self._dirty = True

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #
    def update_plot(self):
        self._drain_buffers()
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
            if self._smooth_enabled and self._smooth_window > 1:
                v = self._smoothed(entry)
            xs, ys = self._downsample(t, v)
            line.set_data(xs, ys)

        if any_data:
            old_xlim = ax.get_xlim()
            old_ylim = ax.get_ylim()
            ax.relim()
            ax.autoscale_view()
            # Preserve user view once set; only autoscale on first data.
            if self._view_set:
                ax.set_xlim(old_xlim)
                ax.set_ylim(old_ylim)
            else:
                self._view_set = True

        # Blit if we can, otherwise a normal idle redraw.
        if not self._blit_enabled or self._background is None:
            self._canvas.draw_idle()
            return

        self._canvas.restore_region(self._background)
        for line in self._lines.values():
            ax.draw_artist(line)
        if self._crosshair.get_visible():
            ax.draw_artist(self._crosshair)
        if self._tip.get_visible():
            ax.draw_artist(self._tip)
        self._canvas.blit(self._ax.bbox)

    def _downsample(self, t, v):
        """View-aware decimation: stride within the visible x-range only.

        Always keeps the first/last sample so axis bounds stay exact, and
        never draws more than ``_MAX_DISPLAY`` points even for huge logs.
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
        stride = seg // self._MAX_DISPLAY
        idx = np.arange(start, stop, stride)
        # anchor the very last point so the line reaches the right edge
        if idx[-1] != stop - 1:
            idx = np.append(idx, stop - 1)
        return t[idx], v[idx]

    def _on_hover(self, event):
        """Show crosshair + tooltip near the nearest data point on hover."""
        if event.inaxes is None or not self._data:
            self._crosshair.set_visible(False)
            self._tip.set_visible(False)
            self._blit_overlay()
            return

        mx = event.xdata
        my = event.ydata
        if mx is None or my is None:
            return

        # Find the closest (t, v) across all loaded signals in DISPLAY
        # space. An x-only comparison snaps to whichever signal has a
        # sample nearest in time — e.g. a 0/1 flag line — even when the
        # cursor sits on a different curve's point. Pixel distance
        # respects both axes.
        to_disp = self._ax.transData.transform
        mouse = to_disp((mx, my))
        best_key = None
        best_idx = 0
        best_d2 = float("inf")
        for sig_key, entry in self._data.items():
            t = entry["t"]
            if t.size == 0:
                continue
            # Snap to the curve actually drawn (smoothed when the filter is
            # on) so the tooltip value matches the visible geometry.
            v = self._display_v(entry)
            # Candidate window: the x-nearest sample plus its neighbours —
            # on a steep segment the pixel-closest point can sit a sample
            # or two away in x.
            idx = min(int(np.searchsorted(t, mx)), t.size - 1)
            lo = max(0, idx - 2)
            hi = min(t.size, idx + 3)
            pts = to_disp(np.column_stack((t[lo:hi], v[lo:hi])))
            d2 = ((pts - mouse) ** 2).sum(axis=1)
            j = int(np.argmin(d2))
            if d2[j] < best_d2:
                best_d2 = float(d2[j])
                best_key = sig_key
                best_idx = lo + j

        if best_key is None:
            self._crosshair.set_visible(False)
            self._tip.set_visible(False)
            self._blit_overlay()
            return

        can_id, sig_name = best_key
        entry = self._data[best_key]
        tx = float(entry["t"][best_idx])
        tv = float(self._display_v(entry)[best_idx])

        self._crosshair.set_xdata([tx, tx])
        self._crosshair.set_visible(True)

        label = f"0x{can_id:03X}/{sig_name}\nt = {tx:.6f} s\nv = {tv:.6g}"
        if self._smooth_enabled and self._smooth_window > 1:
            label += f" (MA{self._smooth_window})"
        self._tip.set_text(label)
        # Place the tooltip beside the data point with a pixel offset so the
        # text box never covers the cursor; flip sides near the axes edges.
        y_lo, y_hi = self._ax.get_ylim()
        ty = max(y_lo, min(y_hi, tv))
        px, py = to_disp((tx, ty))
        ax_bbox = self._ax.bbox
        dx = 14 if px < ax_bbox.x0 + ax_bbox.width / 2 else -14
        dy = 14 if py < ax_bbox.y0 + ax_bbox.height / 2 else -14
        self._tip.set_ha("left" if dx > 0 else "right")
        self._tip.set_va("bottom" if dy > 0 else "top")
        self._tip.set_position(
            self._ax.transData.inverted().transform((px + dx, py + dy))
        )
        self._tip.set_visible(True)

        self._blit_overlay()

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
        """Ensure legend stays as overlay (not affecting axes layout)."""
        leg = self._ax.get_legend()
        if leg is not None and leg.get_in_layout():
            leg.set_in_layout(False)
        # keep our reference in sync
        if leg is not None and leg is not self._legend:
            self._legend = leg
        # The static scene was just rendered — cache it as the blit
        # background. Without this the animated artists (crosshair, tooltip)
        # are never drawn anywhere: a normal render skips them and no blit
        # path can run because _blit_enabled stays False forever.
        self._capture_background()
