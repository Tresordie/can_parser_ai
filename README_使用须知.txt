CAN Bus Parser — macOS 安装说明
================================

安装步骤
--------
1. 打开本 DMG 镜像。
2. 将 "CAN Bus Parser" 图标拖拽到 "Applications" 文件夹。
3. 从启动台或应用程序文件夹启动。

首次打开提示（重要）
--------------------
本应用未经 Apple 公证签名，macOS Gatekeeper 会拦截首次启动：

- 方式一：在 Finder 中找到应用，按住 Control 键点击（或右键）→ 选择"打开"，
  在弹出的对话框中再次点击"打开"。
- 方式二：如果提示"已损坏，无法打开"，请打开终端执行：
      sudo xattr -rd com.apple.quarantine "/Applications/CAN Bus Parser.app"
  输入开机密码后重新打开应用即可。

功能说明
--------
- 离线回放：支持 ASC / BLF / TRC / CSV 等 CAN 日志格式，加载 DBC 后可解码信号并绘图。
- 实时采集：支持 PEAK PCAN-USB 设备。应用已内置 MacCAN PCBUSB 用户态驱动，
  无需额外安装驱动，插上 PCAN-USB 设备后在工具栏选择通道与波特率即可开始采集。
  若提示通道无效，请检查设备是否连接并被系统识别。

运行环境
--------
- macOS 11 及以上（Intel 原生；Apple Silicon 通过 Rosetta 2 运行）。
