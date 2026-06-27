# 版本发布记录 / Release Notes

---

## v0.1.3 (2026-06-27) — Bug 修复与增强 / Bug Fixes & Enhancements

### 🐛 Bug 修复 / Bug Fixes

#### 1. Stop 按钮导致程序崩溃退出（QThread 仍在运行时被销毁）— 严重

共修复了三条触发该问题的代码路径：

**a) 工具栏 Stop（实时模式）**
`_stop()` 在设置 `self._worker = None` 前未等待 `CanWorker` 线程退出。线程最多需要 100ms（`CanWorker.run()` 中的 `time.sleep(0.1)`）才能响应停止信号——在此期间立即丢弃引用会触发 GC 销毁一个仍在运行的 QThread。

**b) LogView Stop（回放模式）**
`_stop_playback()` 从未接触 `self._worker`——若用户曾启动实时采集然后切换至回放模式，`CanWorker` 线程一直处于运行状态。点击 Stop 时仅清理了 `_ParseThread`/`_ReplayThread`，`CanWorker` 被遗漏，最终被 GC 销毁。

**c) `_ReplayThread` 长间隔休眠**
当 CAN 日志文件存在较大时间戳间隔（如数秒甚至数分钟的消息空白）时，`_ReplayThread.run()` 会为整个间隔调用单次 `msleep()`。点击 Stop 后，`wait(10000)` 的 10 秒超时远不足以覆盖长时间休眠——线程在 `msleep()` 中挂起时被销毁。

**修复：**
- `_stop()` (实时模式)：现在在丢弃引用前调用 `self._worker.wait(2000)`
- `_stop_playback()` (回放模式)：现在也会停止 `CanWorker` 并 `wait(2000)`
- `_ReplayThread.run()`：长时间休眠改为每次 100ms 的分块休眠，每块之间检查 `_stop` 标志，使 `wait()` 在约 100ms 内返回

> 涉及文件：`main.py` — `_stop()`, `_stop_playback()`<br>
> 涉及文件：`can_backend.py` — `_ReplayThread.run()`

### ✨ 新增功能 / New Features

#### 2. 信号图悬浮提示（Hover Tooltip）

鼠标悬停在信号波形上时，自动显示十字准线（垂直虚线）和提示框，内容包含：
- 信号名称（`CAN_ID/SignalName` 格式）
- 精确时间戳（`t = x.xxxxxx s`）
- 信号物理值（`v = xxxxx`）

鼠标移出图表区域时，十字准线和提示框自动隐藏。

采用 `np.searchsorted` 二分查找在所有信号的全分辨率数据中定位最近数据点，即使面对 750k+ 数据点 × 多个信号也能实现即时响应。提示框与 blitting 渲染管线正确集成，防止定时器驱动的图表刷新期间的闪烁。

> 涉及文件：`signal_plot.py` — `__init__()`, `_on_hover()`, `update_plot()`

---

## v0.1.2 (2026-06-26) — Bug 修复 / Bug Fixes

### 🐛 Bug 修复 / Bug Fixes

#### 1. 多路复用报文短帧无法解码（严重）
**问题：** 当 CAN 日志中某帧的 DLC 小于 DBC 定义的消息长度时（例如 `MC_EcuInfo` 定义 8 字节但实际 DLC=3 或 DLC=4），该帧被直接丢弃，导致 `MC_EcuInfoMultiplexor: 0` 和 `MC_EcuInfoMultiplexor: 12` 对应的信号完全无法解析。

**原因：** `_ParseThread.run()` 和 `_decode()` 两处均使用严格的 `len(msg.data) >= msg_def.length` 校验，拒绝了所有 DLC 小于 DBC 定义长度的帧。

**修复：** 移除严格长度校验。 `_decode()` 改为仅检查 `len(msg.data) == 0`；`_ParseThread.run()` 改为仅检查 `len(msg.data) > 0`。`cantools.decode(allow_truncated=True)` 会安全处理数据不足的情况。

> 涉及文件：`can_backend.py` — `_decode()`, `_ParseThread.run()`

#### 2. 回放模式下点击 Stop 程序崩溃退出（严重）
**问题：** 日志解析完成后点击 Stop 按钮，程序自动退出并报 `QThread: Destroyed while thread is still running`。

**原因：**
- 工具栏 Stop 按钮（`_stop()`）在 playback 模式下不做任何操作，无法停止回放
- `_stop_internal_threads()` 在停止线程前未断开信号连接，`QThread.finished` 信号在 `deleteLater()` 后仍被处理，导致线程对象在"已调度删除"状态下被重复操作

**修复：**
- `_stop_internal_threads()` 在 `stop()`/`wait()` 前先 `disconnect` 信号（`finished`, `parsed_ready`, `message_with_data`），消除竞态条件
- `_on_playback_done()` 增加 `if not self._running: return` 守卫，防止重复发射 `stopped`
- 工具栏 `_stop()` 在 playback 模式下正确委托给 `_stop_playback()` 执行清理

> 涉及文件：`can_backend.py` — `_stop_internal_threads()`, `_on_playback_done()`<br>
> 涉及文件：`main.py` — `_stop()`

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
