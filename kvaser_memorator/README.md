# Kvaser ASC CAN Log 拼接工具

## 简介

本工具用于将 **Kvaser Memorator** 等CAN日志采集设备导出的**分段 ASC 格式 CAN log 文件**，按时间顺序拼接为**一份完整的 log 文件**，并自动调整时间戳，确保时间轴连续无错位。

## 问题背景

Kvaser Memorator 在长时间记录时，会将 CAN 数据分段存储为多个 ASC 文件。每个分段文件的：
- **时间戳独立**：都从 0 开始计算（absolute 模式）
- **header 独立**：各有自己的起始日期时间

直接拼接这些文件会导致：
1. **时间戳重复**：多个文件的时间戳都从 0 开始，拼接后时间轴重叠
2. **顺序错乱**：文件名顺序不一定等于时间顺序

本工具通过解析 ASC header 中的起始时间自动排序，并重新计算时间戳偏移量，使合并后的时间轴保持连续。

## 功能特性

| 功能 | 说明 |
|------|------|
| 自动扫描 | 扫描指定目录下所有 `.asc` / `.ASC` 文件 |
| 智能排序 | 按 header 中的起始时间排序（或按文件名排序） |
| 时间戳调整 | 后续文件的时间戳自动加上偏移量，接续前文件末尾时间 |
| 格式兼容 | 支持 `absolute` 和 `relative` 两种时间戳模式 |
| 格式检测 | 自动检测 `hex`/`dec` 进制及时间戳模式不一致的情况并警告 |
| 精度保持 | 替换时间戳时保留原始小数位精度 |

## 环境要求

- **Python**: 3.7+
- **依赖**: 无第三方依赖（仅使用标准库）

## 快速开始

### 基本用法

```bash
python merge_asc_logs.py <输入目录> [输出文件] [--sort-by name|time]
```

### 示例

```bash
# 合并 ./asc_logs 目录下所有 ASC 文件，输出到默认文件 merged_output.asc
python merge_asc_logs.py ./asc_logs

# 指定输出文件名
python merge_asc_logs.py ./asc_logs combined_log.asc

# 按文件名排序（适用于文件名含序号的情况）
python merge_asc_logs.py ./asc_logs combined_log.asc --sort-by name
```

## 命令行参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `input_dir` | 位置参数 | 是 | - | 包含分段 ASC 文件的目录路径 |
| `output_file` | 位置参数 | 否 | `merged_output.asc` | 输出文件路径 |
| `--sort-by` | 可选参数 | 否 | `time` | 文件排序方式：`time`=按header起始时间，`name`=按文件名 |

## ASC 文件格式说明

ASC (ASCII) 是 Vector CANalyzer/CANoe 定义的 CAN 日志格式，被 Kvaser Memorator Tools 等多种工具支持。

### 文件结构

```
date Mon Apr 10 09:00:00.000 am 2023      ← 起始时间
base hex  timestamps absolute              ← 数值进制 + 时间戳类型
internal events logged                     ← 内部事件标志
// version 8.2.1                           ← 版本号（可选）
0.000001 CAN 1 Status:chip status ...      ← 消息行（时间戳 + 数据）
0.100000 1  211  Rx  d 8 01 02 ...
```

### Header 行说明

| 行 | 格式 | 说明 |
|----|------|------|
| `date` | `date <WeekDay> <Month> <Day> <HH:MM:SS.usec> [am/pm] <Year>` | 日志起始时间，支持12/24小时制 |
| `base` | `base <hex\|dec> timestamps <absolute\|relative>` | 数值进制和时间戳类型 |
| `internal` | `internal events logged` | 是否记录内部事件 |
| `version` | `// version x.x.x` | CANalyzer/CANoe 版本号 |

### 时间戳模式

| 模式 | 说明 | 示例 |
|------|------|------|
| `absolute` | 时间戳表示从日志起始时刻开始的绝对秒数 | `0.000001`, `1.234567` |
| `relative` | 时间戳表示与上一事件的时间差（delta） | `0.001000`, `0.000500` |

## 时间戳调整原理

### absolute 模式

```
文件A:  0.000001 ... 0.300000   (时间戳不变)
文件B:  0.000001 ... 0.500000   (原始时间戳)

偏移量 = 文件A末尾 + gap - 文件B首帧
       = 0.300000 + 0.000001 - 0.000001
       = 0.300000

文件B调整后:  0.300001 ... 0.800000   ✓ 时间轴连续
```

### relative 模式

```
文件A:  0.001000, 0.000500, 0.000300  (delta序列)
        → 绝对时间: 0.001000, 0.001500, 0.001800

文件B:  0.001000, 0.000200  (delta序列)
        → 从 0.001800 开始累加: 0.002800, 0.003000   ✓ 时间轴连续
```

## 输出示例

运行脚本后的控制台输出：

```
找到 3 个ASC文件:
  - segment_001.asc
  - segment_002.asc
  - segment_003.asc
  解析: segment_001.asc  起始时间=2023-04-10 09:00:00  首帧TS=1e-06  末帧TS=120.5  base=hex  ts_mode=absolute
  解析: segment_002.asc  起始时间=2023-04-10 09:02:00  首帧TS=1e-06  末帧TS=118.3  base=hex  ts_mode=absolute
  解析: segment_003.asc  起始时间=2023-04-10 09:04:00  首帧TS=1e-06  末帧TS=115.7  base=hex  ts_mode=absolute

排序后的合并顺序:
  [1] segment_001.asc  (start=2023-04-10 09:00:00)
  [2] segment_002.asc  (start=2023-04-10 09:02:00)
  [3] segment_003.asc  (start=2023-04-10 09:04:00)

合并完成！输出文件: merged_output.asc
总行数: 15842
```

## 文件结构

```
kvaser_memorator/
├── merge_asc_logs.py    # 主脚本
└── README.md            # 本文档
```

## 注意事项

1. **时间戳精度**：ASC 文件中的时间戳精度通常为微秒级（6位小数），脚本会保持该精度
2. **大文件处理**：脚本将整个文件内容加载到内存中处理，对于超大文件（数百MB）可能需要较多内存
3. **编码问题**：脚本使用 UTF-8 编码读取，遇到无法解码的字节会用替换字符处理
4. **格式一致性**：建议确保所有分段文件使用相同的 `base`（hex/dec）和 `timestamps`（absolute/relative）设置

## 许可证

本工具为开源工具，可自由使用和修改。
