# 版本发布记录 / Release Notes

---

## v0.1.5 (2026-09-08) — 图例颜色修复 / Legend Color Fix

### 🐛 Bug 修复 / Bug Fixes

#### 1. 图例颜色样本不显示颜色（中等）

**问题：** 未选中任何曲线时，右上角图例中各 CAN ID 前的颜色样本几乎不可见（呈淡灰色），无法与曲线颜色对应。

**原因：** 图例句柄是 `_rebuild_legend()` 时刻曲线属性的快照。常见触发路径：点击树中某信号高亮（其他曲线淡化至 alpha 0.12）→ 再勾选新信号 → 图例在淡化状态下重建，0.12 的透明度被永久烘焙进旧信号句柄；之后即使取消高亮、曲线恢复全色，图例句柄仍停留在淡化状态。

**修复：** `_rebuild_legend()` 重建后强制所有句柄 alpha=1.0——图例始终显示真实颜色，选中状态改由文字粗体/着色表达；若重建时高亮仍激活，则把选中项的加粗/着色样式重新应用到新图例文字上，高亮状态不丢失。

> 涉及文件：`signal_plot.py` — `_rebuild_legend()`

### 📦 分发 / Distribution

- 新增 Windows 独立运行包（PyInstaller onefile）：`CAN_Bus_Parser.exe`（约 68MB），未签名，首次运行需过 SmartScreen；实时采集仍需目标机器安装 PEAK 驱动
- README 打包命令补充 `--add-data "can-bus.png;."`（冻结环境下图标资源定位依赖此参数）

---

## v0.1.4 (2026-09-08) — Bug 修复、性能与健壮性 / Bug Fixes, Performance & Robustness

### 🐛 Bug 修复 / Bug Fixes

#### 1. 回放解析完成后信号图将起点与终点连成直线（严重）

**问题：** 加载本地 CAN 日志解析绘制完成后，信号曲线上出现一条从曲线起点贯穿到终点的直线。

**原因：** 解析完成后 `load_parsed_series()` 已通过 `set_series()` 将勾选信号的全量历史灌入信号图，随后 `_ReplayThread` 逐帧重新发出，`LiveView._flush_buffer()` 无条件调用 `plot.add_point()` 把同样的点再次追加——数组变成 `[全量历史, 全量历史]`，折线在两份之间画出回绕直线。

**修复：** `_flush_buffer()` 增加模式守卫：回放模式下信号图由预解码索引驱动，跳过 `add_point()`，回放行只进数据表格。

> 涉及文件：`live_view.py` — `_flush_buffer()`

#### 2. 悬浮十字准线与提示框从未渲染（严重）

**问题：** 鼠标悬停在信号图上时，v0.1.3 加入的十字准线与提示框完全不可见。

**原因：** 两个 artist 标记为 `animated=True`（仅 blitting 路径会绘制），而 blitting 管线自 v0.1.1 重构后断裂——`_capture_background()` 无任何调用点，`_blit_enabled` 永远为 `False`，`update_plot` 的 blit 分支不可达，普通渲染又会跳过 animated artist。

**修复：** `_on_draw()`（draw_event）在每次全量渲染后调用 `_capture_background()` 缓存静态场景；新增 `_blit_overlay()`，`_on_hover()` 改为走轻量 blit 路径（restore_region + draw_artist，约 10ms → 与全量重绘 85ms 相比大幅下降）并真正渲染出十字线与提示框。

> 涉及文件：`signal_plot.py` — `_on_draw()`, `_capture_background()`, `_blit_overlay()`, `_on_hover()`

#### 3. 悬停提示吸附到错误信号（中等）

**问题：** 鼠标悬停在电压曲线上（y≈3.3），提示框却显示另一条 0/1 标志信号的 `v = 0`。

**原因：** `_on_hover()` 的最近点搜索只比较 x（时间）距离，忽略鼠标 y 位置——同一时刻附近多条信号都有采样点时，选中的是时间上最近的而非视觉上最近的。

**修复：** 最近点搜索改为屏幕像素空间的双轴距离（`ax.transData.transform` 换算后比较），每个信号在 x 最近采样点附近取 ±2 候选窗口。

> 涉及文件：`signal_plot.py` — `_on_hover()`

#### 4. 窗口四周出现"聚焦框"亮边（中等）

**问题：** 窗口处于活动状态时四周出现一圈细亮色描边，深色界面上非常刺眼，看起来像控件的聚焦框。

**原因：** 本版本开发过程中曾为无边框窗口（`Qt.FramelessWindowHint`）重注 `WS_THICKFRAME` 原生样式以找回 Aero Snap（拖到屏幕顶部自动最大化、边缘拖拽调整大小）。DWM 会为带 thickframe 的活动窗口绘制非客户区亮色轮廓线，即使设置 `DWMWA_NCRENDERING_POLICY = DISABLED` 在 Win10 19045 上也无法完全压制。此外 `main()` 给顶层窗口挂了 `QGraphicsDropShadowEffect` 蓝色辉光——Qt 不支持对顶层窗口应用 QGraphicsEffect，会引发绘制残留，视觉上也是一圈亮边。

**修复：** 移除整套原生 Snap 机制（`showEvent()` 样式注入、`nativeEvent()` 的 WM_NCCALCSIZE/WM_NCHITTEST 处理、`changeEvent()` 外溢补偿）与顶层窗口辉光效果。窗口管理回到自绘标题栏方案：拖动标题栏移动、最大化/还原按钮、双击标题栏最大化/还原。取舍：不再支持拖到屏幕顶部自动最大化与窗口边缘拖拽调整大小。

> 涉及文件：`main.py` — `MainWindow`, `main()`

#### 5. 悬浮提示框盖住鼠标指针（轻微）

**问题：** 鼠标悬停在曲线上时，显示横/纵轴数值的提示框正好画在鼠标指针上，指针与数据点都被遮挡。

**原因：** 提示框锚点直接设在吸附到的数据点坐标上、没有任何偏移，而文本默认从锚点向右上方展开——吸附逻辑保证鼠标就在该点附近，文本框必然盖住指针。

**修复：** 锚点先换算为像素坐标、加 14px 斜向偏移后再反算回数据坐标；并按锚点所在绘图区象限自动翻转展开方向（左右、上下），提示框始终贴在光标斜侧、既不遮指针也不越出绘图区。

> 涉及文件：`signal_plot.py` — `_on_hover()`

### ⚡ 性能优化 / Performance

#### 6. 实时采集 `add_point` 逐点 `np.append` 为 O(n²)（严重）

每个采样点都触发整个 numpy 数组拷贝：实测累计 30k 点耗时 323ms、120k 点 4477ms（对比 list 缓冲 + 批量转换的 2ms/12ms，差距 132~379 倍）。修复后点先进入 Python list 缓冲，由 `update_plot`（250ms 定时）批量并入 numpy 数组，实测 30k 点仅 34ms（O(1)/点）。

> 涉及文件：`signal_plot.py` — `add_point()`, `_drain_buffers()`, `_new_entry()`

#### 7. 其他热点（中等）

- **状态栏逐帧 setText**：`Messages: N` 标签按每帧（500-1000fps）重排，改为 250ms 定时刷新
- **空转 CanWorker 线程移除**：`workers.py` 的轮询循环体为空（消息实际走 Notifier 推送），整个线程纯浪费，连同 `main.py` 相关创建/等待代码一并移除
- **表格 flush 批量化**：100ms flush 内逐行 `insertRow` 触发表头 ResizeToContents 逐行重测——改为一次性 `setRowCount` 批量分配行、resize 模式换为 Interactive + 约 1 次/秒的 `resizeColumnsToContents` 节流；`_rebuild_table()` 复用已有 QTableWidgetItem
- **回放批量 emit**：`_ReplayThread` 逐行跨线程 emit 在密集日志下会淹没 GUI 事件队列——改为按 1000 行/事件边界批量发射，跨线程调用下降两个数量级
- **解析流式解码**：`messages = list(reader)` 全量物化（75 万帧约 200MB）改为边读边解码，进度按已解析帧数显示
- **series 分段转 numpy**：解析期间每信号用 Python float 列表攒到最后才转换（约 0.5GB 瞬时开销）——改为每个进度节拍把已有列表转为 numpy 块，结束时 `concatenate`

> 涉及文件：`main.py`、`workers.py`（删除）、`live_view.py`、`can_backend.py`、`signal_plot.py`

#### 8. 滚轮缩放 / 拖动平移卡顿（严重）

**问题：** 鼠标滚轮放大缩小信号图（含点击横轴锁定单轴后的滚轮缩放）时画面明显卡顿，快速滚动后即使停止操作，UI 仍会持续冻结较长时间。

**原因：** 每个滚轮/拖动事件都同步调用 `draw()` 做全画布重绘——24 信号实测一帧 200~280ms，事件排队逐个付费；剖析显示每帧成本大头不是数据点数（点数几乎不影响），而是图例（24 个条目每帧重新测量文本布局，约 150ms）与 constrained_layout 每帧重解布局（约 50ms）。另外缩放后曲线要等 250ms 定时器才按新视野重抽稀，期间重绘的是旧视野数据。

**修复：** 交互事件全部改为 `draw_idle()`（同一轮事件循环内合并为一次重绘）；canvas 交互回调接入 `_on_view_interact()`，事件到达即按新视野重抽稀各条曲线；滚轮/拖动事件持续到达期间临时隐藏图例（≥8 条曲线时才隐藏，避免无谓闪烁），事件停止 180ms 后恢复并补一次全量重绘。实测每个滚轮事件处理耗时从 ~200-300ms 降至 4-8ms。

> 涉及文件：`signal_plot.py` — `_ScrollZoomCanvas.wheelEvent()`, `mouseMoveEvent()`, `_on_axis_click()`, `_on_view_interact()`, `_restore_legend()`

### 🛡 健壮性 / Robustness

#### 9. 乱序时间戳防御（中等）

分段/合并生成的日志可能携带乱序时间戳，会导致折线画花并破坏绘图内部依赖单调性的 `searchsorted` 搜索。解析完成后对每个信号序列做稳定 `argsort`（仅检测到乱序时），行数据同理稳定排序（O(n) 预检，有序时零开销）。

> 涉及文件：`can_backend.py` — `_emit_progress()`, `_ensure_sorted_rows()`

#### 10. 其他（轻微）

- **解析失败后 LogView 卡死**：错误路径不复位按钮状态（Play 禁用无法重试）——`error_occurred` 统一进入 `_on_backend_error()`，复位 LogView 按钮并显示错误
- **`start_live` 启动竞态**：`_raw_messages` 清空与 `_running=True` 原先在 Notifier 创建之后，启动初期的帧会丢失或落入旧缓冲——已移到 Notifier 之前，且 `start_live()` 返回成功与否、`main._start()` 据此决定是否进入 Live 状态
- **`stop()` 重复 emit**：部分路径会连续两次调用 `stop()` 导致 `stopped` 重复发射、表格双重 flush——仅在确有会话运行时发射

> 涉及文件：`can_backend.py` — `start_live()`, `stop()`, `_ParseThread.run()`；`main.py` — `_start()`, `_on_backend_error()`

### ✨ 新增功能 / New Features

#### 11. 信号图滑动平均滤波（显示层平滑，可开关）

**问题：** 温度等量化信号在图上呈阶梯/毛刺状，缩放到全览时难以观察趋势。

**方案：** Signal Plot 底栏新增 `Smooth` 开关与窗口点数（3-999 pts，默认 9）：

- 居中滑动平均（部分窗口处理边界），O(n) 向量化计算、无相位偏移、端点无幅度衰减；按信号缓存平滑结果，仅在数据变化或窗口调整时重算
- 纯显示层滤波：悬浮十字线/提示框吸附并显示平滑值（标注 `MA窗口`），原始序列、数据表格、CSV 导出完全不受影响；实时采集与回放两种模式下均实时生效
- 开关切换即时重绘，开关往返可随时恢复原始曲线
- **默认开启**，开关状态与窗口大小通过 QSettings 持久化，重启应用后保持上次设置

> 涉及文件：`signal_plot.py` — `set_smoothing()`, `_moving_average()`, `_display_v()`, `_smoothed()`, `update_plot()`, `_on_hover()`；`live_view.py` — 底栏控件

#### 12. 界面视觉精修（质感提升）

在保留 GitHub Dark 配色体系的前提下重写全局样式表，重点打磨细节：

- **图形元素改为运行时绘制**：下拉箭头、SpinBox 上下箭头、树展开箭头、勾选/半选标记、标题栏最小化/最大化/还原/关闭符号全部由 `QPainter` 抗锯齿绘制成 PNG（同时生成 `@2x` 版本供高分屏使用，配合 `AA_UseHighDpiPixmaps`），启动时写入系统临时目录，箭头/勾选注入 QSS、窗口按钮通过 `QIcon` 使用。顺带修掉了下拉箭头因 `::drop-down::down-arrow` 选择器写法不规范、CSS 三角技巧失效而显示为一段灰色横条的老问题，也替换掉了依赖字体回退、渲染质量不稳定的 Unicode 符号（− □ ❐ ✕）
- **文字与字体**：标题栏改为纯文本 "CAN Bus Parser"（去掉 ⟐ 装饰符），Start / Stop 按钮去掉 ▶ ■ 前缀；应用字体统一为 Segoe UI 9pt（12px，Windows 标准 UI 字号）并加入 Microsoft YaHei UI 回退，`QLabel` 全局 12px、表格正文 12px，与 QSS 中各控件字号一致——原先默认字体 10pt 与 12px 控件混排，"Legend:" 这类未被 QSS 覆盖的标签比旁边控件大一号
- **控件风格**：下拉框改为按钮式外观（带 hover/展开态）；普通按钮加细腻纵向渐变，Start/Stop/Parse 分别为绿/红/蓝主操作色并统一 hover/pressed/disabled 态；Tab 改为下划线导航式；树与表格选中行改为半透明蓝（`rgba(31,111,235,0.55)`）并支持整行高亮；勾选框、SpinBox、滚动条（10px 细轨、圆角滑块）、菜单、工具提示、状态栏全部纳入主题
- **布局与留白**：内容区四周 8px 留白，左右面板间距 6px，标题栏加高至 36px 并给图标留出 8px 内边距，工具栏内边距/间距加大，分隔符可见；表格最后一列自动铺满剩余宽度
- **数据表格可读性**：浮点值显示改为最多 10 位有效数字（`-486.20000000000005` → `-486.2`），仅影响表格显示，CSV 导出保持原始精度

> 涉及文件：`main.py` — `STYLESHEET`, `_build_ui_icons()`, `_glyph_icon()`, `build_stylesheet()`, `_TitleBar`, `_create_toolbar()`, `_init_ui()`, `_create_central_layout()`, `main()`；`live_view.py` — `_fmt_value()`, 底栏 SpinBox 宽度, 表头 stretch；`log_view.py` — Parse/Stop 按钮 objectName

### 🧹 工程卫生 / Housekeeping

- `requirements.txt`：补上被直接 import 却未声明的 `numpy`；移除全项目未引用的 `uptime`；`pyinstaller` 注明为打包工具
- 新增 `.gitignore`（`__pycache__/`、`*.pyc`、`dist/`、`build/`、`.zcode/`），停止跟踪 `.pyc`
- README 运行路径更正；项目结构移除 `workers.py`
- 本版本各修复/优化均以离屏 Qt 无头回归脚本验证通过（`_verify_*.py`，属过程文件，验证后已清理）

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

#### 3. 图例高亮残留 Bug — 选中新信号后旧信号图例未退出高亮（中等）

**问题：** 在树形控件中点击选择一个信号时，信号图中的曲线正确切换高亮（新信号加粗、旧信号恢复正常），但图例（Legend）中新旧信号的文字同时保持粗体/着色——旧信号的高亮没有退出。

**原因：** `_reset_highlight()` 和 `_highlight()` 方法直接使用 `self._legend` 引用来修改图例文字属性。当 `_rebuild_legend()` 被其他代码路径（如 `set_signals`、`add_signal_instance`、窗口大小调整）调用时，旧图例通过 `_legend.remove()` 从 matplotlib 坐标轴中移除，并创建新图例。若 `_reset_highlight()` 在 `_rebuild_legend()` 之后但在下一个 `draw_event` 同步之前运行，`self._legend` 可能指向一个已从坐标轴分离的图例对象——对其文字属性的修改不会反映在渲染中。而 `self._ax.get_legend()` 始终返回当前实际显示的图例。

**修复：** 新增 `_sync_legend()` 辅助方法，在每次修改图例文字属性前从 `self._ax.get_legend()` 重新获取当前图例引用。在 `_reset_highlight()`、`_highlight()` 和 `_on_click()` 三处调用该方法，确保始终操作实际渲染的图例对象。同时将原有的 `hasattr` 守卫替换为 `_sync_legend()` 调用后加空值检查。

> 涉及文件：`signal_plot.py` — `_sync_legend()`, `_reset_highlight()`, `_highlight()`, `_on_click()`

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
