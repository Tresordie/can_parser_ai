# 版本发布记录 / Release Notes

---

## v0.1.1 (2026-06-24) — Bug 修复与增强 / Bug Fixes & Enhancements

### 🐛 Bug 修复 / Bug Fixes

#### 1. 图例高亮切换 Bug（严重）
**问题：** 单击图例标签时，`_on_click`（button_press_event）和 `_on_pick`（pick_event）两个事件处理函数在同一物理点击上先后触发，导致高亮被立即取消（toggle 效应）。用户每次点击图例，信号线短暂高亮后迅速恢复原状。

**修复：** 在 `_highlight()` 中检测目标信号线是否已经是当前高亮线，若是则直接返回不做任何操作，彻底消除了 toggle 行为。同时 `_on_pick` 增加守护判断，跳过已被 `_on_click` 处理的 event。

> 涉及文件：`signal_plot.py` — `_highlight()`, `_on_pick()`

#### 2. 空白区域点击后视觉不更新（严重）
**问题：** 在图表空白区域点击以取消高亮时，`_reset_highlight()` 正确重置了内部状态，但缺少 `_canvas.draw()` 调用，导致界面不刷新——用户看到的高亮线未消失，直到下一次鼠标交互才更新。

**修复：** 在 `_on_click()` 的空白区域分支中，`_reset_highlight()` 之后添加 `self._canvas.draw()`，确保视觉状态与内部状态同步。

> 涉及文件：`signal_plot.py` — `_on_click()`

#### 3. 图例 ↔ 图表 ↔ 信号树 三点联动验证
**验证：** 编写 `_verify_legend_sync.py` 集成测试脚本，模拟图例点击，断言三个区域同步高亮：
- 图例文字 → 加粗 + 着色
- 图表曲线 → 线宽 3.5、zorder 100、其他曲线 alpha 0.12
- 信号树 → 对应信号项被选中并滚动到可见区域

确认三个区域高亮稳定一致。

> 新增文件：`_verify_legend_sync.py`

---

## v0.1 (2026-06-06) — 初始版本 / Initial Release

### 🎯 核心功能 / Core Features

#### 实时采集 / Live Capture
- PCAN-USB 硬件实时 CAN 报文读取（`python-can` PCAN 接口）
- 支持 PCAN_USBBUS1 ~ PCAN_USBBUS8 通道选择
- 支持 125k / 250k / 500k / 1000k 波特率选择
- DBC 加载后自动解码，实时显示信号物理值
- 后台轮询线程（`CanWorker`），不阻塞 UI

#### 离线回放 / Offline Playback
- 多格式支持：ASC / BLF / TRC / CSV (信号) / CSV (SavvyCAN 帧)
- 两阶段回放架构：
  - `_ParseThread`：后台线程一次性全量解析日志，构建预解码信号索引
  - `_ReplayThread`：按时间戳驱动回放，仅消费索引（不重复解码）
- Play / Stop 控制，状态联动的按钮启用逻辑

#### 预解码信号索引 / Pre-decoded Signal Index
- 全量解析后构建 `_signal_series` 字典：`{sig_name: (t_numpy_array, v_numpy_array)}`
- 后续勾选新信号时 O(1) 即时加载，无需重新解析日志文件
- 大幅提升交互响应速度（解析 53MB ASC 日志后，任何信号秒级加载）

#### 信号选择 / Signal Selection
- 树形展示 DBC 所有报文和信号（`QStandardItemModel` + `QTreeView`）
- 级联复选框逻辑：勾选/取消父节点自动应用到子节点，子节点变化更新父节点（全选/部分选/未选）
- 多路复用信号支持：分组在 `[mux=N]` 可折叠节点下，复用指示信号标记 `[MUX]`
- 搜索过滤：按信号名或 CAN ID 搜索，支持多路复用组内搜索
- 全选 / 取消全选批量操作

#### 实时数据表格 / Real-time Data Table
- 两种显示模式：
  - 原始帧视图（无信号勾选时）：Timestamp | CAN ID | DLC | Data
  - 解码信号视图（勾选信号后）：Timestamp | 0xID/SigName 列
- 100ms 缓冲刷新定时器，批量处理到达的消息，避免逐帧 UI 更新
- 最多保留 1000 行（最近数据）
- Silent fill 优化（`setUpdatesEnabled(False)` 避免中间态渲染）

#### 信号时序图 / Interactive Signal Plot
- Matplotlib 嵌入 PyQt5（`FigureCanvasQTAgg`）
- 深色主题（`#0d1117` 背景，GitHub Dark 风格配色）
- 滚轮缩放（鼠标位置感知：x 轴附近仅水平缩放，y 轴附近仅垂直缩放，中间区域双向缩放）
- 轴锁定：单击 x 轴（Time）或 y 轴（Value）边框锁定/解锁缩放方向
- 左键拖动平移
- 图例高亮：单击图例标签高亮对应曲线（线宽 3.5、zorder 100），其他曲线淡化（alpha 0.12）
- 图例自动重排：根据信号数量动态调整列数（最多 7 列，适用于 34+ 信号场景）
- 图例字体大小控制：4-20 pt 调节旋钮

#### 性能优化 / Performance Optimizations
- **Blitting 渲染**：仅修改过的 artist 在缓存背景上重绘，大幅减少每帧绘制开销
- **视口感知降采样**：当可见 x 范围超过 `_MAX_DISPLAY`（10,000 点）时，仅在该范围内跨步采样，保留首尾样本以保证精确轴边界
- **批量数据加载**：`set_series()` 一次性接收 numpy 数组，O(1) 赋值，无逐点追加开销
- **CSV 导出后台线程**：大文件导出不冻结 UI，含进度提示

#### 数据导出 / Data Export
- 双模式导出：
  - 实时模式：导出原始 CAN 帧为 ASC / CSV 标准日志
  - 回放模式：导出已解码信号值为 CSV
- 后台线程导出，避免 UI 冻结

#### 用户界面 / User Interface
- 无边框自定义标题栏（`_TitleBar`）：最小化/最大化/关闭按钮、拖拽移动、双击最大化
- 窗口发光阴影效果（蓝色调 `#1f6feb`）
- 深色主题样式表（~260 行 QSS）：覆盖所有 Qt 组件，GitHub Dark 风格
- 应用图标（`can-bus.png`）在标题栏和任务栏显示
- Segoe UI 字体，10pt
- 工具栏布局：DBC 文件选择、通道选择、波特率选择、Start/Stop 按钮
- 状态栏：显示当前模式、通道、波特率等实时状态

#### 信号实例 / Signal Instances
- 右键上下文菜单："Add copy of {signal} to plot"
- 同一信号可添加多个实例到图表，以 `[n]` 后缀区分
- 每个实例独立配色

#### DBC 文件支持 / DBC File Support
- 通过 `cantools.database.load_file()` 加载标准 DBC 文件
- 预构建 `{frame_id: message}` 映射表，解码时 O(1) 查找
- 示例 DBC：`cosmo.dbc`（电动车，191 条报文）

### 📋 已知限制 / Known Limitations
- 仅支持 PCAN 硬件（不支持 Vector、Kvaser、SocketCAN 等）
- 不支持 CAN FD
- 不支持 UDS 诊断协议
- 回放速度固定 1x（不支持倍速播放）
- 信号图可视范围最多同时显示 10,000 个数据点（超出自动降采样）
- 数据表格最多保留 1,000 行
- 实时采集模式仅支持 Windows（PCAN 驱动限制）；回放模式跨平台可用

### 🛠 技术栈 / Tech Stack
| 组件 | 版本 | 用途 |
|------|------|------|
| Python | 3.8+ | 运行环境 |
| PyQt5 | >= 5.15 | GUI 框架 |
| python-can | >= 4.3 | CAN 总线抽象层 |
| cantools | >= 39.0 | DBC 解析与信号解码 |
| matplotlib | >= 3.7 | 信号时序图渲染 |
| numpy | - | 高效数值计算 |
| PyInstaller | - | 独立可执行文件打包 |

### 📁 项目结构 / Project Structure
```
can_parser/
├── main.py                 # 应用入口、主窗口、标题栏、工具栏、样式表
├── can_backend.py          # CAN 后端：PCAN 采集、多格式回放、信号解码、索引
├── dbc_loader.py           # DBC 加载、树形模型、级联选择、多路复用支持
├── live_view.py            # 实时数据视图：数据表 + 信号图标签页
├── log_view.py             # 日志回放控制面板
├── signal_plot.py          # Matplotlib 交互式信号时序图（blitting + 降采样）
├── workers.py              # 后台轮询线程
├── requirements.txt        # Python 依赖
├── can-bus.png             # 应用图标
├── cosmo.dbc               # 示例 DBC（电动车，191 条报文）
├── num8_combined.asc       # 示例 ASC 日志
└── CHANGELOG.md            # 本文件
```
