# CAN Bus Parser v0.1

A PyQt5 + python-can + cantools desktop tool for CAN bus data acquisition and offline analysis.

[中文版](README_zh.md)

## Features

| Module | Description |
|--------|-------------|
| **Live Capture** | Real-time CAN message reading via PCAN hardware with automatic DBC decoding |
| **Offline Playback** | Replay ASC / BLF / TRC / CSV (signal) / CSV (SavvyCAN frame) log formats |
| **Signal Selection** | Tree view of all messages and signals after DBC load, with search and batch select |
| **Data Table** | Real-time scrolling table of selected signal values, with CSV export |
| **Signal Plot** | Interactive time-series plot with zoom, pan, axis lock, and legend highlighting |

## Requirements

- Python 3.8+
- Windows 10+ (PCAN driver requirement)
- PEAK PCAN-USB hardware (required for live capture only; playback mode works without hardware)

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

### 5. Data Export

On the Data Table tab, click **Save CSV** to export the current table data.

## Standalone Builds

Pre-built standalone executables are available for Windows, Linux, and macOS. No Python installation required.

### Building from source

```bash
# Windows
build.bat

# Linux / macOS
bash build.sh
```

Output will be in `dist/CAN_Bus_Parser/`.

## Project Structure

```
can_parser/
├── main.py              # Entry point, main window, title bar, toolbar, status bar, stylesheet
├── can_backend.py       # CAN backend: PCAN capture, multi-format playback, signal decoding
├── dbc_loader.py        # DBC file loader, tree signal model, cascading checkbox logic
├── live_view.py         # Live data view: data table + signal plot tabs
├── log_view.py          # Log playback control panel
├── signal_plot.py       # Matplotlib interactive signal time-series plot
├── workers.py           # Background polling thread
├── can_parser.spec      # PyInstaller spec for cross-platform standalone builds
├── build.bat            # Windows build script
├── build.sh             # Linux / macOS build script
├── requirements.txt     # Python dependencies
├── can-bus.png          # Application icon
```

## Architecture

```
main.py (MainWindow)
  ├── DbcLoader: DBC parsing → QStandardItemModel → QTreeView
  ├── CanBackend: python-can wrapper, capture/playback/decode
  │     ├── CanWorker: background polling thread
  │     └── _PlaybackThread: log playback thread
  ├── LiveView: QTabWidget
  │     ├── Data Table (QTableWidget): live signal values, 100ms buffer flush
  │     └── Signal Plot (SignalPlot): Matplotlib interactive chart
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
- Signal plot displays up to 50,000 data points (auto-downsamples beyond that)
- Data table retains up to 1,000 rows
- Windows only for live capture (PCAN driver limitation); playback works cross-platform

## Changelog

### v0.1 (2026-06-06)

- PCAN live capture with DBC signal decoding
- ASC / BLF / TRC / CSV log playback
- Tree-based signal search and batch selection
- Real-time data table with CSV export
- Interactive signal plot (zoom/pan/axis lock/legend highlight)
- Frameless custom title bar with app icon
- FiraCode Nerd Font monospace, light theme
- Cross-platform standalone builds via PyInstaller

## License

MIT
