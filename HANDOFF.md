# 项目交接文档 / Project Handoff

> 最后更新：2026-11-20（v0.1.8）。面向接手本项目的开发者或后续 AI 会话：读完本文档即可了解项目全貌、关键设计决策与历史踩坑，避免重复踩坑。

---

## 1. 项目概览

**CAN Bus Parser** — 基于 PyQt5 + python-can + cantools 的 CAN 总线数据采集与离线分析桌面工具（Windows 优先）。

- 当前版本：**v0.1.8**（版本唯一来源：`main.py` 顶部 `__version__`）
- 仓库：GitHub `Tresordie/can_parser_ai` + Gitee `simonyuan2019/can_parser_ai`（origin 配置了双 push URL，`git push origin master` 一次同时推送两端）
- 完整版本历史见 [CHANGELOG.md](CHANGELOG.md)；用户视角文档见 [README.md](README.md) / [README_zh.md](README_zh.md)

## 2. 技术栈

| 依赖 | 用途 |
|------|------|
| PyQt5 >= 5.15 | GUI 框架（Fusion 风格 + QSS 深色主题，无边框自绘标题栏） |
| python-can >= 4.3 | CAN 抽象层：PCAN 实时接口 + LogReader 多格式日志读取 |
| cantools >= 39.0 | DBC 解析与信号解码（含多路复用） |
| matplotlib >= 3.7 | 信号时序图（blitting 渲染 + 视口感知降采样） |
| numpy | 解析索引与信号序列 |

Python 3.8+，实时采集依赖 PEAK PCAN-USB 硬件与驱动（仅 Windows）；回放模式无需硬件、跨平台。

## 3. 模块地图

```
main.py (~1080 行)      应用入口 + MainWindow + 自绘标题栏 _TitleBar + QSS 样式表 + 启动时渲染 UI 字形图标
can_backend.py          CanBackend：PCAN 采集 / 多格式回放 / cantools 解码 / 预解码信号索引(numpy) / CSV+ASC 导出
dbc_loader.py           DbcLoader：DBC → QStandardItemModel 树模型；三级级联勾选(消息→mux组→信号)；mux 分组构建
live_view.py            LiveView：Data Table + Signal Plot 双 Tab；实时缓冲刷新；CSV 导出(后台线程)
signal_plot.py          SignalPlot：交互式 matplotlib 图（缩放/平移/轴锁/图例高亮/悬停提示/blitting/降采样/平滑）
log_view.py             LogView：日志文件选择 + Play/Stop 控件
```

数据流：`PCAN / 日志文件 → python-can → CanBackend._decode() (cantools) → message_received 信号 → LiveView 缓冲(100ms flush) → 数据表 + 信号图`。回放走两阶段：`_ParseThread` 全量解码建索引 → `_ReplayThread` 按时间戳回放。

## 4. 关键设计不变量（改动前必读）

这些是历史上真实踩过的坑，对应 CHANGELOG 各版本，改动相关代码时务必保持：

1. **版本号单一来源** — 只改 `main.py.__version__`，标题栏/窗口标题自动同步（v0.1.6 起）。
2. **回放模式不得重复喂点** — `_flush_buffer()` 的 `feed_plot = mode != 'playback'` 守卫必须保留：回放时信号图已由预解码索引 (`set_series`) 批量灌入，`_ReplayThread` 的行只能进数据表，再 `add_point` 会画出首尾回绕直线（v0.1.4）；同理别把 `self._plot` 局部别名删掉却留下调用（v0.1.7 崩溃回归）。
3. **blitting 管线完整性** — `animated=True` 的 artist（十字线/提示框）只能经 blit 路径绘制；每次全量渲染后 draw_event 必须调用 `_capture_background()`，否则悬停层永远不可见（v0.1.4 教训）。
4. **树过滤统一走 `_apply_filters()`**（v0.1.8 起）— 搜索文本与 Selected Only 两条规则在此合并计算。新增任何树过滤/显示逻辑必须并入该函数，不要另起 `setRowHidden` 散点调用；它同时挂在 `_sync_checked_signals()` 末尾，勾选变化后即时刷新。
5. **勾选防抖** — 树 itemChanged → `cascade_check_state` → 80ms 单发 `_sync_timer` → `_sync_checked_signals()`。批量勾选（Select All）靠它合并成一次同步；回放启动前有显式 flush 防抖逻辑，勿删。
6. **图例句柄是快照** — 重建图例时所有句柄 alpha 必须强制 1.0，激活高亮的文字样式需重新套用，否则淡化透明度被永久烘焙（v0.1.5）。
7. **悬停吸附用显示空间** — 最近点搜索必须在像素空间比较双轴距离，数据空间会因轴比例不同吸错信号（v0.1.4）。
8. **表格与导出分离** — Data Table 只保留最近 `MAX_TABLE_ROWS=1000` 行；CSV 导出永远读 backend 全量 parsed 数据（含 raw view 全信号导出语义，见 `_save_parsed_csv` docstring）。
9. **线程生命周期** — 所有后台线程（_ParseThread/_ReplayThread/CSV 导出线程）停止需 `wait()`；`_ReplayThread` 100ms 分块休眠 + `_stop` 标志；`MainWindow.closeEvent` 统一兜底，防止 `QThread: Destroyed while thread is still running` 崩溃（v0.1.2/v0.1.3）。
10. **UI 字形运行时渲染** — QSS 无法画形状，箭头/勾选/窗口控件符号由 `_build_ui_icons()` 启动时渲染 PNG（1x + @2x），模板占位符 `@name@` 在 `build_stylesheet()` 中替换；Unicode 符号方案已废弃（字体回退不可控）。
11. **打包参数是硬要求** — PyInstaller 必须带 `--add-data "can-bus.png;."`（冻结环境图标定位）和 `--exclude-module` ML 大包清单（torch 等，见 README 构建命令），否则构建失败或爆炸。完整命令见 README「Standalone Builds」。

## 5. 开发与验证方法

项目没有正式测试框架，验证方式为**离屏冒烟测试**（无需硬件、无需显示器）：

```bash
# 环境变量 QT_QPA_PLATFORM=offscreen 下：
# 1. 构造 QApplication + MainWindow
# 2. 临时写一个含普通消息 + mux 消息的最小 DBC，调 _dbc_loader.load()
# 3. 直接操作 item.setCheckState / 按钮.click()，QEventLoop 等待防抖定时器
# 4. 用 QTreeView.isRowHidden(row, parent_index) 断言过滤结果
```

v0.1.8 即用此方式验证了 8 个场景（过滤/搜索叠加/mux/全选联动）。改 UI 逻辑建议沿用此模式先跑一遍再交付。涉及 PCAN 实时采集的改动无法自动化验证，需真机（PEAK 硬件）确认。

## 6. 发版清单（Release Checklist）

1. `main.py.__version__` → 新版本号
2. `CHANGELOG.md` 顶部加新版本条目（中英双语标题风格，写明需求/原因/方案/验证）
3. `README.md` + `README_zh.md`：标题版本号、功能表、涉及的使用说明、底部版本历史各加一条
4. （可选）PyInstaller 重新打包 exe（产物在 `dist/`，不入库）
5. 提交信息格式沿用惯例：`v0.1.x: 一句话英文描述`
6. `git push origin master` — 一次推送同时到达 GitHub 与 Gitee（双 push URL）

## 7. 已知限制与备注

- 仅支持 PCAN 硬件接口（Vector/Kvaser 等未支持）；无 CAN FD；无 UDS；回放固定 1x
- 信号图可视范围最多 10,000 点（超出自动降采样）；数据表最多 1,000 行
- README「项目结构」中列出的 `cosmo.dbc`、`num8_combined.asc` 示例文件当前不在仓库中（文档与实际目录有出入，待清理或补文件）
- `interact.md` 是历史问题备忘、`prompt.md` 是无关的提示词模板，均不影响运行
- 无 CI、无 lint 配置；依赖锁版本靠 `requirements.txt` 下限写法
