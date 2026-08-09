# CAN Bus Parser v0.1.4

A PyQt5 + python-can + cantools desktop tool for CAN bus data acquisition and offline analysis.

[中文版](README_zh.md)

## Features

| Module | Description |
|--------|-------------|
| **Live Capture** | Real-time CAN message reading via PCAN hardware with automatic DBC decoding |
| **Offline Playback** | Replay ASC / BLF / TRC / CSV (signal) / CSV (SavvyCAN frame) log formats |
| **Signal Selection** | Tree view of all messages and signals after DBC load, with search and batch select |
| **Data Table** | Real-time scrolling table of selected signal values, with CSV export |
| **Signal Plot** | Interactive time-series plot with zoom, pan, axis lock, legend highlight, and hover tooltip |

## Requirements

- Python 3.8+ (running from source)
- Windows 10+ or macOS 11+ — the macOS DMG ships with the PCAN-USB driver, so live capture works on both platforms
- PEAK PCAN-USB hardware (required for live capture only; playback mode works without hardware)
- See [CHANGELOG.md](CHANGELOG.md) for detailed release notes

## Installation

### macOS — pre-built DMG (recommended)

Download `CAN_Bus_Parser_macOS_x86_64.dmg`, open it, and drag **CAN Bus Parser** into **Applications**. The MacCAN PCBUSB user-space driver for PCAN-USB is bundled — live capture works without installing any driver.

The app is ad-hoc signed (not Apple-notarized), so the first launch is intercepted by Gatekeeper: right-click the app → **Open** → **Open** again. If macOS reports the app is "damaged", run in Terminal:

```bash
sudo xattr -rd com.apple.quarantine "/Applications/CAN Bus Parser.app"
```

### From source

```bash
pip install -r requirements.txt
```

### Dependencies

| Package | Purpose |
|---------|---------|
| PyQt5 >= 5.15 | GUI framework |
| python-can >= 4.3 | CAN bus abstraction (PCAN interface + LogReader) |
| cantools >= 39.0 | DBC parsing and signal decoding |
| matplotlib >= 3.7 | Signal time-series plotting |

## Usage

```bash
python main.py
```

### 1. Load a DBC File

Click the `...` button next to `DBC:` in the toolbar and select a `.dbc` file. The tree view on the left will show all messages and signals:

```
Messages / Signals
├── MC_Status (0x100)
│   ├── MC_Speed
│   ├── MC_Torque
│   └── MC_Temp
├── BMS_Voltage (0x200)
│   ├── BMS_PackVolt
│   └── BMS_PackCurr
└── ...
```

Check the signals you want to monitor. Use the search box to filter by name or CAN ID.

### 2. Live Capture

1. Select a **Channel** (PCAN_USBBUS1 ~ PCAN_USBBUS8)
2. Select a **Bitrate** (125k / 250k / 500k / 1000k)
3. Click **Start**

Captured data appears in real time in the data table and signal plot.

### 3. Offline Playback

1. Click the **Log File...** button at the bottom and select a CAN log file
2. Click **Play** to start playback
3. Click **Stop** to halt

Supported log formats:

| Format | Description |
|--------|-------------|
| `.asc` | Vector CANalyzer ASCII log |
| `.blf` | Vector binary log format |
| `.trc` | CANoe/CANalyzer trace format |
| `.csv` (signal) | First line is `CSV signals`, one decoded signal per column |
| `.csv` (frame) | SavvyCAN exported raw frame format (Time/ID/Data columns) |

### 4. Signal Plot Interaction

- **Scroll-wheel zoom**: Inside plot area → both axes; near x-axis → horizontal only; near y-axis → vertical only
- **Axis lock**: Click the x-axis (Time) or y-axis (Value) spine to lock zoom to that axis. Click again to unlock
- **Drag pan**: Left-click and drag to pan the view
- **Legend highlight**: Click a signal name in the legend to highlight that line and dim all others
- **Hover tooltip**: Move the mouse over the waveform to see a crosshair and tooltip showing signal name, exact timestamp, and value at that point

### 5. Data Export

On the Data Table tab, click **Save CSV** to export the current table data.

## Standalone Builds

### macOS DMG (one-shot script)

```bash
bash build_dmg.sh
```

Runs the full pipeline — icon generation, PyInstaller build (`can_parser.spec`, bundles the PCAN driver dylib plus a runtime hook), ad-hoc codesign, offscreen smoke test, and DMG creation. Output: `dist/CAN_Bus_Parser_macOS_x86_64.dmg`.

### Windows / generic (PyInstaller)

Pre-built standalone executables can also be generated directly via PyInstaller:

```bash
pyinstaller --onefile --windowed --icon=can-bus.png --name "CAN_Bus_Parser" main.py
```

Output will be in `dist/CAN_Bus_Parser/`.

## Project Structure

```
can_parser/
├── main.py              # Entry point, main window, title bar, toolbar, status bar, stylesheet
├── can_backend.py       # CAN backend: PCAN capture, multi-format playback, signal decoding, index
├── dbc_loader.py        # DBC file loader, tree signal model, cascading checkbox logic, mux support
├── live_view.py         # Live data view: data table + signal plot tabs, CSV export
├── log_view.py          # Log playback control panel
├── signal_plot.py       # Matplotlib interactive signal time-series plot (blitting + min-max downsampling)
├── requirements.txt     # Python dependencies
├── build_dmg.sh         # One-shot macOS packaging script (build → sign → smoke test → DMG)
├── can_parser.spec      # PyInstaller spec (bundles PCAN driver dylib + runtime hook)
├── hook-dyld-path.py    # Runtime hook: expose bundled dylibs to find_library
├── can-bus.png          # Application icon
├── cosmo.dbc            # Example DBC (EV, 191 messages)
├── num8_combined.asc    # Example ASC log
└── CHANGELOG.md         # Detailed release notes
```

## Architecture

```
main.py (MainWindow)
  ├── DbcLoader: DBC parsing → QStandardItemModel → QTreeView
  ├── CanBackend: python-can wrapper, capture/playback/decode
  │     ├── _ParseThread: background full-log decoder → signal index (payload decode cache)
  │     └── _ReplayThread: timestamp-driven playback from decoded index (batched emission)
  ├── LiveView: QTabWidget
  │     ├── Data Table (QTableWidget): live signal values, 100ms buffer flush
  │     └── Signal Plot (SignalPlot): Matplotlib interactive chart with blitting
  └── LogView: log file selection + play/stop controls
```

Data flow:

```
PCAN hardware / Log file
    │
    ▼
python-can (Notifier/LogReader)
    │
    ▼
CanBackend._decode() → cantools decoding
    │
    ▼
message_received_batch signal (batched rows) ──→ LiveView buffer ──→ Data Table + Signal Plot
```

## Known Limitations

- PCAN hardware only; Vector, Kvaser, and other interfaces are not supported
- No CAN FD support
- No UDS diagnostics
- Playback speed is fixed at 1x
- Signal plot displays up to 10,000 data points in visible range (auto-downsamples beyond that)
- Data table retains up to 1,000 rows (most recent)
- Live capture works on Windows and macOS (the macOS DMG bundles the PCBUSB driver); Apple Silicon runs the x86_64 build via Rosetta 2
- The macOS build is ad-hoc signed and not Apple-notarized — first launch requires Gatekeeper confirmation

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for full details.

### v0.1.4 (2026-08-09)

- **Feature:** macOS DMG distribution — standalone `.app` with the MacCAN PCBUSB PCAN-USB driver bundled; live capture works out of the box on macOS
- **Feature:** One-shot packaging script `build_dmg.sh` (PyInstaller + ad-hoc signing + smoke test + DMG)
- **Perf:** Blitting actually enabled now (background capture wired into `draw_event`); hover tooltip blitted; zoom/pan coalesced via `draw_idle`
- **Perf:** Min-max downsampling replaces stride decimation — step signals keep their spikes
- **Perf:** Live ingestion O(n²) → amortised O(1) (chunked buffers); plot refresh 4 Hz → 10 Hz
- **Perf:** Live capture and replay deliver rows in batches (~50 ms windows) via `message_received_batch`; parse-time payload decode cache (200k-frame log ≈ 3.7 s)
- **Perf:** Data-table overflow rebuilt in bulk instead of per-row `removeRow(0)`
- **Fix:** Packaged app crash right after log parsing (SIGSEGV in Qt raster engine — `QGraphicsDropShadowEffect` vs high-frequency blit repaints); window glow effect removed
- **Cleanup:** Removed idle `CanWorker` polling thread; added `.gitignore`

### v0.1.3 (2026-06-27)

- **Fix:** Stop button crash (`QThread: Destroyed while thread is still running`) fixed in all three code paths: live mode toolbar Stop, playback mode LogView Stop, and long sleep in `_ReplayThread`
- **Fix:** `_ReplayThread` now sleeps in 100ms chunks with `_stop` flag checks, preventing `wait()` timeout on logs with large timestamp gaps
- **Fix:** `_stop()` and `_stop_playback()` now properly `wait(2000)` for `CanWorker` thread before dropping the reference
- **Fix:** Legend highlight persistence — clicking a tree node to select a new signal now properly clears the previous signal's legend highlight via `_sync_legend()` helper
- **Feature:** Hover tooltip on signal plot — crosshair + tooltip showing signal name, timestamp, and value at mouse position

### v0.1.2 (2026-06-26)

- **Fix:** Short DLC frames in multiplexed messages (e.g. `MC_EcuInfo` DLC=3/4 vs DBC-defined 8) are now decoded instead of silently dropped
- **Fix:** Stop button crash after log playback (`QThread: Destroyed while thread is still running`) — signal disconnection before thread cleanup + `_stop()` now handles playback mode
- **Fix:** Toolbar Stop button now correctly stops log playback in addition to live capture

### v0.1.1 (2026-06-24)

- **Fix:** Legend highlight toggle bug — `_on_click` + `_on_pick` double-fire on single click no longer cancels highlight
- **Fix:** Clicking empty plot area now properly updates visual state (missing `_canvas.draw()` added)
- **Verify:** Legend ↔ plot ↔ tree three-way highlight sync confirmed stable
- **Verify:** Integration test script (`_verify_legend_sync.py`) added

### v0.1 (2026-06-06)

- PCAN live capture with DBC signal decoding
- ASC / BLF / TRC / CSV log playback with pre-decoded signal index
- Tree-based signal search, batch selection, and cascading checkbox logic
- Real-time data table with dual-mode CSV export (raw frames / decoded signals)
- Interactive signal plot (zoom/pan/axis lock/legend highlight) with blitting + view-aware downsampling
- Frameless custom title bar with app icon and glow shadow
- Dark theme (GitHub Dark inspired), Segoe UI font
- Multiplexed signal support, signal instance duplicates, legend font size control
- PyInstaller standalone executable support

## License

MIT
