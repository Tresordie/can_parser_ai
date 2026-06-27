# CAN Bus Parser v0.1.3

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

- Python 3.8+
- Windows 10+ (PCAN driver requirement)
- PEAK PCAN-USB hardware (required for live capture only; playback mode works without hardware)
- See [CHANGELOG.md](CHANGELOG.md) for detailed release notes

## Installation

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
cd simonyuan_projects/can_parser
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

Pre-built standalone executables can be generated via PyInstaller.

### Building from source

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
├── signal_plot.py       # Matplotlib interactive signal time-series plot (blitting + downsampling)
├── workers.py           # Background polling thread
├── requirements.txt     # Python dependencies
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
  │     ├── CanWorker: background polling thread (live mode)
  │     ├── _ParseThread: background full-log decoder → signal index
  │     └── _ReplayThread: timestamp-driven playback from decoded index
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
message_received signal ──→ LiveView buffer ──→ Data Table + Signal Plot
```

## Known Limitations

- PCAN hardware only; Vector, Kvaser, and other interfaces are not supported
- No CAN FD support
- No UDS diagnostics
- Playback speed is fixed at 1x
- Signal plot displays up to 10,000 data points in visible range (auto-downsamples beyond that)
- Data table retains up to 1,000 rows (most recent)
- Windows only for live capture (PCAN driver limitation); playback works cross-platform

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for full details.

### v0.1.3 (2026-06-27)

- **Fix:** Stop button crash (`QThread: Destroyed while thread is still running`) fixed in all three code paths: live mode toolbar Stop, playback mode LogView Stop, and long sleep in `_ReplayThread`
- **Fix:** `_ReplayThread` now sleeps in 100ms chunks with `_stop` flag checks, preventing `wait()` timeout on logs with large timestamp gaps
- **Fix:** `_stop()` and `_stop_playback()` now properly `wait(2000)` for `CanWorker` thread before dropping the reference
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
