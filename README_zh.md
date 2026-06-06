# CAN Bus Parser v0.1

基于 PyQt5 + python-can + cantools 的 CAN 总线数据采集与离线分析桌面工具。

[English](README.md)

## 功能概览

| 模块 | 功能 |
|------|------|
| **实时采集** | PCAN 硬件实时读取 CAN 报文，按 DBC 自动解码 |
| **离线回放** | 支持 ASC / BLF / TRC / CSV(信号) / CSV(SavvyCAN帧) 格式日志回放 |
| **信号选择** | DBC 加载后树形展示所有报文和信号，支持搜索、全选/取消 |
| **数据表格** | 实时滚动表格显示已选信号值，支持 CSV 导出 |
| **信号图** | 交互式信号时序图，支持缩放/平移/轴锁定/图例高亮 |

## 环境要求

- Python 3.8+
- Windows 10+（PCAN 驱动依赖）
- PEAK PCAN-USB 硬件（实时采集时需要，回放模式无需硬件）

## 安装

```bash
pip install -r requirements.txt
```

### 依赖项

| 包 | 用途 |
|----|------|
| PyQt5 >= 5.15 | GUI 框架 |
| python-can >= 4.3 | CAN 总线抽象层（PCAN 接口 + LogReader） |
| cantools >= 39.0 | DBC 解析与信号解码 |
| matplotlib >= 3.7 | 信号时序图渲染 |

## 使用方式

```bash
cd simonyuan_projects/can_parser
python main.py
```

### 1. 加载 DBC 文件

点击工具栏 `DBC:` 右侧的 `...` 按钮，选择 `.dbc` 文件。加载后左侧树形视图显示所有报文和信号：

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

勾选需要查看的信号（可搜索过滤）。

### 2. 实时采集

1. 选择 **Channel**（PCAN_USBBUS1 ~ PCAN_USBBUS8）
2. 选择 **Bitrate**（125k / 250k / 500k / 1000k）
3. 点击 **Start**

采集到的数据会实时显示在数据表和信号图中。

### 3. 离线回放

1. 点击底部 **Log File...** 按钮，选择 CAN 日志文件
2. 点击 **Play** 开始回放
3. 点击 **Stop** 停止

支持的日志格式：

| 格式 | 说明 |
|------|------|
| `.asc` | Vector CANalyzer ASCII 日志 |
| `.blf` | Vector 二进制日志格式 |
| `.trc` | CANoe/CANalyzer Trace 格式 |
| `.csv` (信号) | 首行为 `CSV signals`，每列一个已解码信号 |
| `.csv` (帧) | SavvyCAN 导出的原始帧格式（含 Time/ID/Data 列） |

### 4. 信号图操作

- **滚轮缩放**：光标在绘图区 → 双向缩放；在 x 轴附近 → 水平缩放；在 y 轴附近 → 垂直缩放
- **轴锁定**：单击 x 轴（Time）或 y 轴（Value）边框 → 锁定该轴单独缩放，再次单击取消
- **拖动平移**：左键拖动平移视图
- **图例高亮**：点击图例中的信号名 → 高亮该信号线，其他信号淡化

### 5. 数据导出

在数据表标签页点击 **Save CSV**，将当前表格数据导出为 CSV 文件。

## 独立运行包

提供 Windows / Linux / macOS 的独立可执行文件，无需安装 Python 环境。

### 从源码构建

```bash
# Windows
build.bat

# Linux / macOS
bash build.sh
```

构建产物在 `dist/CAN_Bus_Parser/` 目录下。

## 项目结构

```
can_parser/
├── main.py              # 应用入口，主窗口，标题栏，工具栏，状态栏，样式表
├── can_backend.py       # CAN 后端：PCAN 实时采集、多格式日志回放、信号解码
├── dbc_loader.py        # DBC 文件加载，树形信号模型，级联选择逻辑
├── live_view.py         # 实时数据视图：数据表 + 信号图标签页
├── log_view.py          # 日志回放控制面板
├── signal_plot.py       # Matplotlib 交互式信号时序图
├── workers.py           # 后台轮询线程
├── can_parser.spec      # PyInstaller 跨平台打包配置
├── build.bat            # Windows 构建脚本
├── build.sh             # Linux / macOS 构建脚本
├── requirements.txt     # Python 依赖
├── can-bus.png          # 应用图标
```

## 架构说明

```
main.py (MainWindow)
  ├── DbcLoader: DBC 解析 → QStandardItemModel → QTreeView
  ├── CanBackend: python-can 封装，采集/回放/解码
  │     ├── CanWorker: 后台轮询线程
  │     └── _PlaybackThread: 日志回放线程
  ├── LiveView: QTabWidget
  │     ├── 数据表 (QTableWidget): 实时信号值，100ms 缓冲刷新
  │     └── 信号图 (SignalPlot): Matplotlib 交互式图表
  └── LogView: 日志文件选择 + 播放/停止控件
```

数据流向：

```
PCAN 硬件 / 日志文件
    │
    ▼
python-can (Notifier/LogReader)
    │
    ▼
CanBackend._decode() → cantools 解码
    │
    ▼
message_received 信号 ──→ LiveView 缓冲 ──→ 数据表 + 信号图
```

## 已知限制

- 仅支持 PCAN 硬件，不支持 Vector、Kvaser 等其他接口
- 不支持 CAN FD
- 不支持 UDS 诊断
- 回放速度固定为 1x，不支持倍速播放
- 信号图最多显示 50,000 个数据点（超出自动降采样）
- 数据表最多保留 1,000 行
- 实时采集仅支持 Windows（PCAN 驱动限制）；回放模式跨平台可用

## 版本历史

### v0.1 (2026-06-06)

- PCAN 实时采集与 DBC 信号解码
- ASC / BLF / TRC / CSV 日志回放
- 树形信号搜索与批量选择
- 实时数据表格与 CSV 导出
- 交互式信号时序图（缩放/平移/轴锁定/图例高亮）
- 无边框自定义标题栏，应用图标
- FiraCode Nerd Font 等宽字体，浅色主题
- PyInstaller 跨平台独立运行包

## License

MIT
