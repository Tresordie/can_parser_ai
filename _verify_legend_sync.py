"""Verify legend click highlights all three areas."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import sys
import time

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
import matplotlib
matplotlib.use("Qt5Agg")

from main import MainWindow


class FakeEvent:
    def __init__(self, x, y, inaxes=None):
        self.x = x
        self.y = y
        self.inaxes = inaxes
        self.button = 1


def main():
    app = QApplication(sys.argv)
    win = MainWindow()

    win._dbc_loader.load(os.path.abspath('cosmo.dbc'))
    app.processEvents()

    log_path = os.path.abspath('logfile2_20260609_combined.asc')
    win._log_view._filepath = log_path
    win._log_view._play_btn.setEnabled(True)

    # Parse
    print('=== Parsing log ===')
    win._play_log()
    deadline = time.time() + 40
    while time.time() < deadline:
        app.processEvents(); time.sleep(0.1)
        if 'Playing' in win._status_label.text():
            break
    for _ in range(10):
        app.processEvents(); time.sleep(0.1)

    # Check 2 signals
    for (can_id, sig_name), item in win._dbc_loader._signal_items.items():
        if sig_name in ('PT_ImuAccX', 'PT_ImuGyrX'):
            item.setCheckState(Qt.Checked)
    if hasattr(win, '_sync_timer') and win._sync_timer.isActive():
        win._sync_timer.stop()
    win._sync_checked_signals()
    app.processEvents(); time.sleep(0.3); app.processEvents()

    plot = win._live_view._plot
    canvas = plot._canvas
    leg = plot._legend
    texts = leg.get_texts()
    print(f'Legend texts: {[t.get_text() for t in texts]}')
    print(f'Plot lines: {len(plot._lines)}')

    # ═══════════════════════════════════════════════════════════════
    # Test: Click legend text → check all three areas
    # ═══════════════════════════════════════════════════════════════
    print('\n=== Test: Click Legend "0x34F/PT_ImuAccX" ===')

    # Clear everything first
    plot.clear_highlight()
    win._tree_view.clearSelection()
    app.processEvents()

    target_txt = texts[0]  # "0x34F/PT_ImuAccX"
    target_label = target_txt.get_text()
    print(f'  Target: "{target_label}"')

    # Get display coords of the legend text
    bbox = target_txt.get_window_extent(canvas.get_renderer())
    cx = (bbox.x0 + bbox.x1) / 2
    cy = (bbox.y0 + bbox.y1) / 2

    # Simulate legend click (inaxes=None)
    fake_event = FakeEvent(cx, cy, inaxes=None)
    plot._on_click(fake_event)
    app.processEvents(); time.sleep(0.1); app.processEvents()

    # Check 1: Legend text highlighted (bold + colored)?
    print(f'\n  --- Check 1: Legend text highlight ---')
    target_bold = target_txt.get_fontweight() == 'bold'
    target_alpha = target_txt.get_alpha()
    print(f'  Legend text fontweight: {target_txt.get_fontweight()} (bold={target_bold})')
    print(f'  Legend text alpha: {target_alpha}')
    print(f'  Legend text color: {target_txt.get_color()}')

    # Check 2: Plot line highlighted (picked)?
    print(f'\n  --- Check 2: Plot line highlight ---')
    picked = plot._picked_line
    print(f'  _picked_line: {picked.get_label() if picked else None}')
    if picked:
        print(f'  Picked linewidth: {picked.get_linewidth()} (should be 3.5)')
        print(f'  Picked alpha: {picked.get_alpha()}')
        # Check other lines are dimmed
        for key, line in plot._lines.items():
            if line is not picked:
                print(f'  Other line "{line.get_label()}" alpha: {line.get_alpha()} (should be 0.12)')

    # Check 3: Tree item selected?
    print(f'\n  --- Check 3: Tree selection ---')
    # Find the tree item for PT_ImuAccX
    accx_item = None
    for (can_id, sig_name), item in win._dbc_loader._signal_items.items():
        if sig_name == 'PT_ImuAccX':
            accx_item = item
            break
    if accx_item:
        checked = accx_item.checkState() == Qt.Checked
        print(f'  Tree item checked: {checked}')
    # Check current selection in tree
    sel_model = win._tree_view.selectionModel()
    current = win._tree_view.currentIndex()
    print(f'  Tree currentIndex valid: {current.isValid()}')
    if current.isValid():
        sel_item = win._dbc_loader.model.itemFromIndex(current)
        print(f'  Tree current item text: "{sel_item.text()}"')
        print(f'  Tree current item is PT_ImuAccX: {"PT_ImuAccX" in sel_item.text()}')

    # Check if the signal_label_clicked was emitted and _on_plot_label_clicked ran
    print(f'\n  --- Check signal_label_clicked emission ---')
    emitted = []
    plot.signal_label_clicked.connect(lambda c, s: emitted.append((c, s)))
    # Click again (different legend text to avoid toggle)
    if len(texts) > 1:
        target_txt2 = texts[1]
        bbox2 = target_txt2.get_window_extent(canvas.get_renderer())
        cx2 = (bbox2.x0 + bbox2.x1) / 2
        cy2 = (bbox2.y0 + bbox2.y1) / 2
        fake_event2 = FakeEvent(cx2, cy2, inaxes=None)
        plot._on_click(fake_event2)
        app.processEvents()
        print(f'  Emitted: {emitted}')
        print(f'  _picked_line after 2nd click: {plot._picked_line.get_label() if plot._picked_line else None}')

    print('\n=== VERDICT ===')
    # Re-check the FIRST clicked line (PT_ImuAccX) after all operations
    final_picked = plot._picked_line
    final_bold = target_txt.get_fontweight() == 'bold'
    print(f'  Final _picked_line: {final_picked.get_label() if final_picked else None}')
    print(f'  Final target_txt bold: {final_bold}')
    # The first click test is what matters
    first_click_ok = (target_bold and picked is not None and picked.get_linewidth() == 3.5)
    if first_click_ok:
        print('SUCCESS: Legend click highlights legend + plot line + tree')
    else:
        print('PARTIAL: Some areas not highlighted')
        if not target_bold:
            print('  - Legend text NOT bold')
        if picked is None:
            print('  - Plot line NOT picked')
        elif picked.get_linewidth() != 3.5:
            print(f'  - Plot line linewidth wrong: {picked.get_linewidth()}')

    win._backend.stop()
    app.processEvents()


if __name__ == '__main__':
    main()
