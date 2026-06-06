#!/usr/bin/env python3
"""
merge_asc_logs.py - 拼接Kvaser分段ASC CAN log文件，避免时间戳错位

功能：
  1. 扫描指定目录下所有 .asc 文件
  2. 解析每个ASC文件的 header（date行、base行、internal events行、version行）
  3. 按 header 中的起始日期时间排序文件
  4. 将所有文件的消息行按时间先后顺序合并到一份输出文件
  5. 对后续文件的时间戳加上偏移量，使其接续前一个文件的末尾时间

用法：
  python merge_asc_logs.py <input_dir> [output_file] [--sort-by name|time]

  input_dir  : 包含分段ASC文件的目录
  output_file: 输出文件路径（默认: merged_output.asc）
  --sort-by  : 文件排序方式
               name  - 按文件名排序（适用于文件名含序号的情况）
               time  - 按header中的起始时间排序（默认）

示例：
  python merge_asc_logs.py ./asc_logs
  python merge_asc_logs.py ./asc_logs combined.asc --sort-by name
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────
# ASC 文件解析相关常量与正则
# ──────────────────────────────────────────────

# date 行格式: date Wed Apr 16 09:21:13.159 am 2014
# 或           date Wed Apr 16 21:21:13.159 pm 2014
# 或 24h制:    date Wed Apr 16 13:21:13.159 2014
RE_DATE_LINE = re.compile(
    r"^date\s+"
    r"(?P<weekday>\w+)\s+"
    r"(?P<month>\w+)\s+"
    r"(?P<day>\d+)\s+"
    r"(?P<hour>\d+):(?P<min>\d+):(?P<sec>\d+)(?:\.(?P<usec>\d+))?\s*"
    r"(?:(?P<ampm>am|pm)\s+)?"
    r"(?P<year>\d+)\s*$",
    re.IGNORECASE,
)

RE_BASE_LINE = re.compile(
    r"^base\s+(?P<base>hex|dec)\s+timestamps\s+(?P<ts>absolute|relative)",
    re.IGNORECASE,
)

RE_INTERNAL_LINE = re.compile(r"^internal\s+events\s+logged", re.IGNORECASE)

RE_VERSION_LINE = re.compile(r"^//\s*version\s+[\d.]+")

# 匹配消息行的第一个时间戳（浮点数，如 0.036886 或 2137.317027）
RE_TIMESTAMP = re.compile(r"^\s*(?P<ts>\d+\.\d+)\s")

# 月份名称到数字的映射
MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def parse_date_line(line: str) -> Optional[datetime]:
    """
    解析ASC文件中的date行，提取并返回datetime对象。

    ASC文件的首行记录了日志的起始日期和时间，格式示例如下：
        date Wed Apr 16 09:21:13.159 am 2014   （12小时制 + am/pm）
        date Mon Apr 10 14:30:05.123 2023       （24小时制，无 am/pm）
        date Mon Apr 10 02:24:54.471 pm 2023    （12小时制 + pm，即14:24:54）

    本函数通过 RE_DATE_LINE 正则匹配解析以上三种格式，
    提取年、月、日、时、分、秒、微秒以及 am/pm 标记，
    并统一转换为 Python datetime 对象返回。

    参数:
        line: 文件中的date行文本内容（需以 'date ' 开头）

    返回:
        datetime 对象（解析成功），或 None（格式不匹配时）
    """
    m = RE_DATE_LINE.match(line.strip())
    if not m:
        return None

    # 从正则命名分组中提取各个时间分量
    d = m.groupdict()
    # 月份名称转为数字（如 "Apr" -> 4）
    month = MONTH_MAP.get(d["month"], 1)
    day = int(d["day"])
    hour = int(d["hour"])
    minute = int(d["min"])
    sec = int(d["sec"])
    # 微秒部分（可选，有些ASC文件中不含小数秒）
    usec = int(d["usec"]) if d["usec"] else 0
    year = int(d["year"])

    # ── am/pm 24小时制转换 ──
    # 如果文件使用12小时制，需将 am/pm 转换为24小时制：
    #   - 12:00 am → 00:00（午夜）
    #   - 01:00 am → 01:00（凌晨，不变）
    #   - 12:00 pm → 12:00（中午，不变）
    #   - 02:00 pm → 14:00（下午，加12）
    ampm = d.get("ampm")
    if ampm:
        ampm = ampm.lower()
        if ampm == "am" and hour == 12:
            # 12 am 即午夜0点
            hour = 0
        elif ampm == "pm" and hour != 12:
            # 1~11 pm 加12小时
            hour += 12

    # ── 微秒补齐 ──
    # ASC文件中的小数秒位数不固定（如 .159 只有3位），
    # 需左补零至6位以符合 datetime 微秒参数要求（0~999999）
    # 例：.159  → 159000 ；.000159 → 159
    usec = int(str(usec).ljust(6, "0")[:6])

    try:
        return datetime(year, month, day, hour, minute, sec, usec)
    except ValueError:
        # 日期或时间分量超出合法范围时返回 None
        return None


def extract_first_timestamp(line: str) -> Optional[float]:
    """
    从一行文本中提取行首的时间戳浮点数值（单位：秒）。

    ASC消息行的格式为：
        <时间戳> <通道> <ID> <方向> d <DLC> <数据> ...
    例如：
        0.036886 1  211  Rx  d 8 01 02 ...    → 返回 0.036886
        2137.317027 CAN 1 Status:chip ...       → 返回 2137.317027

    时间戳是行开头的浮点数（整数部分 + 小数部分），
    通过 RE_TIMESTAMP 正则匹配提取。

    参数:
        line: ASC文件中的一行文本

    返回:
        时间戳浮点值（匹配成功），或 None（非消息行、空行等）
    """
    m = RE_TIMESTAMP.match(line)
    if m:
        return float(m.group("ts"))
    return None


def replace_timestamp(line: str, new_ts: float) -> str:
    """
    将消息行开头的时间戳替换为新的时间戳值，同时保留原行其余内容不变。

    替换时保留与原始时间戳相同的小数位数，以维持文件格式一致性。
    例如原始为 "0.100000"（6位小数），则替换后也是6位小数格式。

    参数:
        line:   原始消息行文本
        new_ts: 需要写入的新时间戳值（单位：秒）

    返回:
        替换后的完整行字符串
    """
    m = RE_TIMESTAMP.match(line)
    if not m:
        # 该行无时间戳，原样返回
        return line

    old_ts_str = m.group("ts")
    # ── 保留原始小数位精度 ──
    # 例如原始 "0.036886" → 小数位长度 6
    #      原始 "0.100"    → 小数位长度 3
    if "." in old_ts_str:
        dec_len = len(old_ts_str.split(".")[1])
    else:
        # 整数格式（罕见），默认保留6位小数
        dec_len = 6

    # 按原始精度格式化新时间戳字符串
    new_ts_str = f"{new_ts:.{dec_len}f}"

    # 将行中时间戳部分（m.start("ts") 到 m.end("ts")）替换为新字符串
    # 保持行中其余所有字符（通道号、ID、数据等）不变
    return line[:m.start("ts")] + new_ts_str + line[m.end("ts"):]


class ASCFile:
    """
    表示单个ASC CAN log文件及其解析后的元数据。

    将ASC文件解析为两个部分：
    - header_lines: 文件头部信息行（date、base、internal、version、空行）
    - body_lines:   消息体行（包含时间戳的CAN数据行）

    属性说明:
        filepath        : 文件完整路径
        filename        : 文件名（不含目录）
        start_datetime  : 从header的date行解析出的起始时间（datetime对象）
        header_lines    : 文件头部行列表
        body_lines      : 文件消息体行列表
        first_ts        : 第一条消息的时间戳（秒）
        last_ts         : 最后一条消息的时间戳（秒）
        base            : 数值进制，'hex' 或 'dec'
        timestamp_mode  : 时间戳类型，'absolute'（绝对时间）或 'relative'（相对前一事件）
    """

    def __init__(self, filepath: str):
        """初始化ASCFile，设定文件路径并预设默认属性值。"""
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        # 起始时间，由 parse() 中解析 date 行填充
        self.start_datetime: Optional[datetime] = None
        # header 与 body 的行内容（parse() 填充）
        self.header_lines: list[str] = []
        self.body_lines: list[str] = []
        # 首尾时间戳，parse() 中扫描 body_lines 时记录
        self.first_ts: Optional[float] = None
        self.last_ts: Optional[float] = None
        # 默认值：base 为十六进制，时间戳为绝对模式
        self.base: str = "hex"  # hex or dec
        self.timestamp_mode: str = "absolute"  # absolute or relative

    def parse(self):
        """
        读取并解析ASC文件，将内容分离为 header 和 body 两部分。

        解析规则：
        - 文件开头的连续 'header 行' 包括：
          ① date 行（起始时间）
          ② base 行（数值进制与时间戳类型）
          ③ internal events logged 行
          ④ // version x.x.x 注释行
          ⑤ 以上行之间的空行
        - 遇到第一条不符合以上 header 格式的行时，视为 body 开始
        - body 中所有带时间戳的行，均记录 first_ts 和 last_ts

        返回: self（支持链式调用，如 af.parse().filename）
        """
        in_header = True
        # 以 utf-8 编码读取，无法解码的字节用 replacement 字符替代
        with open(self.filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()

                if in_header:
                    # ── 判断当前行是否属于 header ──

                    # ① date 行：记录日志起始时间
                    if stripped.startswith("date "):
                        dt = parse_date_line(stripped)
                        if dt:
                            self.start_datetime = dt
                        self.header_lines.append(line)
                        continue

                    # ② base 行：指定数值进制和时间戳类型
                    #    例如 "base hex  timestamps absolute"
                    m = RE_BASE_LINE.match(stripped)
                    if m:
                        self.base = m.group("base")           # 'hex' 或 'dec'
                        self.timestamp_mode = m.group("ts")   # 'absolute' 或 'relative'
                        self.header_lines.append(line)
                        continue

                    # ③ "internal events logged" 行
                    if RE_INTERNAL_LINE.match(stripped):
                        self.header_lines.append(line)
                        continue

                    # ④ "// version x.x.x" 注释行（CANalyzer/CANoe v7.0+）
                    if RE_VERSION_LINE.match(stripped):
                        self.header_lines.append(line)
                        continue

                    # ⑤ header 内部的空行（保留，不视为 body 开始）
                    if stripped == "":
                        self.header_lines.append(line)
                        continue

                    # 以上均不符合 → 视为 body 的第一行
                    in_header = False

                # ── body 部分：消息行（CAN 数据、Status、ErrorFrame 等）──
                self.body_lines.append(line)

                # 提取该行的时间戳（如果有），用于计算偏移量
                ts = extract_first_timestamp(line)
                if ts is not None:
                    if self.first_ts is None:
                        # 记录第一条带时间戳消息的时间戳
                        self.first_ts = ts
                    # 持续更新，最终记录最后一条消息的时间戳
                    self.last_ts = ts

        return self


def merge_asc_files(
    input_dir: str,
    output_file: str,
    sort_by: str = "time",
):
    """
    合并指定目录下所有ASC文件到一个输出文件，确保时间戳连续无错位。

    整体处理流程：
    ┌────────────────────────────────────────────────────────────────┐
    │  1. 扫描目录，查找所有 .asc / .ASC 文件                              │
    │  2. 解析每个文件的 header（起始时间、进制、时间戳模式）                │
    │  3. 按起始时间（或文件名）排序，确定合并顺序                           │
    │  4. 检查各文件格式是否一致（hex/dec, absolute/relative）              │
    │  5. 拼接文件内容，并调整后续文件的时间戳，使其接续前文件末尾时间       │
    │  6. 写入合并后的输出文件                                        │
    └────────────────────────────────────────────────────────────────┘

    时间戳调整策略（核心）：

    ── absolute 模式 ──
    每个分段文件的消息时间戳都是从0开始的绝对秒数。
    合并时，后续文件的时间戳需加上偏移量：
        offset = 前文件的最后时间戳 + gap(0.000001s) - 本文件的第一个时间戳

    示例：
        文件A: 0.000001 ... 0.300000
        文件B: 0.000001 ... 0.500000
        偏移量 = 0.300000 + 0.000001 - 0.000001 = 0.300000
        文件B 合并后: 0.300001 ... 0.800000  ✓ 时间轴连续

    ── relative 模式 ──
    每行的时间戳表示与上一事件的时间差（delta）。
    合并时，将 relative 时间戳累加转换为绝对时间戳，
    从 cumulative_offset 开始累加，确保时间轴无缝衔接。

    参数:
        input_dir   : 包含分段ASC文件的目录路径
        output_file : 合并后的输出文件路径
        sort_by     : 'time'（按header起始时间排序）或 'name'（按文件名排序）
    """

    # ══════════════════════════════════════════════════════════════════
    # 第1步：扫描目录，查找所有 ASC 文件
    # ══════════════════════════════════════════════════════════════════
    # 先尝试小写扩展名 .asc，若无结果再尝试大写 .ASC
    asc_paths = sorted(Path(input_dir).glob("*.asc"))
    if not asc_paths:
        # 部分系统（如某些Kvaser导出工具）可能生成大写扩展名文件
        asc_paths = sorted(Path(input_dir).glob("*.ASC"))
    if not asc_paths:
        print(f"错误: 在目录 '{input_dir}' 中未找到 .asc 文件", file=sys.stderr)
        sys.exit(1)

    print(f"找到 {len(asc_paths)} 个ASC文件:")
    for p in asc_paths:
        print(f"  - {p.name}")

    # ══════════════════════════════════════════════════════════════════
    # 第2步：解析每个ASC文件的header和body
    # ══════════════════════════════════════════════════════════════════
    asc_files: list[ASCFile] = []
    for p in asc_paths:
        af = ASCFile(str(p))
        af.parse()
        asc_files.append(af)
        # 打印解析摘要，便于排查问题
        print(f"  解析: {af.filename}  "
              f"起始时间={af.start_datetime}  "
              f"首帧TS={af.first_ts}  末帧TS={af.last_ts}  "
              f"base={af.base}  ts_mode={af.timestamp_mode}")

    # ══════════════════════════════════════════════════════════════════
    # 第3步：确定文件合并顺序
    # ══════════════════════════════════════════════════════════════════
    if sort_by == "name":
        # 按文件名排序（适用于文件名含序号的情况，如 log_001.asc, log_002.asc）
        asc_files.sort(key=lambda f: f.filename)
    else:
        # 按header中的起始日期时间排序
        # 若某个文件解析不到时间，以 datetime.min（最早时间）兜底，
        # 相同时间的文件再按文件名排序作为次级排序键
        asc_files.sort(key=lambda f: (f.start_datetime or datetime.min, f.filename))

    print(f"\n排序后的合并顺序:")
    for i, af in enumerate(asc_files):
        print(f"  [{i+1}] {af.filename}  (start={af.start_datetime})")

    # ══════════════════════════════════════════════════════════════════
    # 第4步：格式一致性检查
    #   各分段的 base(hex/dec) 和 timestamps(absolute/relative) 应当一致，
    #   不一致时发出警告（不中断合并，但可能导致输出文件解析异常）
    # ══════════════════════════════════════════════════════════════════
    first_base = asc_files[0].base
    first_ts_mode = asc_files[0].timestamp_mode
    for af in asc_files[1:]:
        if af.base != first_base:
            print(f"警告: 文件 {af.filename} 的 base={af.base} "
                  f"与首个文件的 base={first_base} 不一致，可能产生问题", file=sys.stderr)
        if af.timestamp_mode != first_ts_mode:
            print(f"警告: 文件 {af.filename} 的 timestamps={af.timestamp_mode} "
                  f"与首个文件的 timestamps={first_ts_mode} 不一致", file=sys.stderr)

    # ══════════════════════════════════════════════════════════════════
    # 第5步：合并文件内容并调整时间戳
    #
    # 合并策略：
    #   - 以第一个文件的 header 作为整个输出文件的 header
    #     （后续文件的 header 被丢弃，因为合并后只有一份日志）
    #   - 第一个文件的 body 原样追加，时间戳不变
    #   - 后续文件 body 中的每一行，其时间戳加上计算好的偏移量
    #
    # 变量说明：
    #   cumulative_offset : 累计时间偏移量（单位：秒）
    #                       表示“到目前为止已处理过的最后一个时间戳”
    #   gap               : 文件间最小间隔，防止时间戳重叠（0.000001秒）
    # ══════════════════════════════════════════════════════════════════
    output_lines: list[str] = []

    # ── 写入输出文件的 header（使用第一个文件的 header）──
    output_lines.extend(asc_files[0].header_lines)

    # 累计时间偏移量，表示已处理部分的“时间轴末尾”
    cumulative_offset = 0.0

    for idx, af in enumerate(asc_files):
        if idx == 0:
            # ── 第一个文件：时间戳原样输出，无需调整 ──
            output_lines.extend(af.body_lines)
            # 记录第一个文件的最后时间戳，作为下一个文件的偏移起点
            if af.last_ts is not None:
                cumulative_offset = af.last_ts
        else:
            # ── 后续文件：计算偏移量并调整时间戳 ──
            if af.timestamp_mode == "absolute":
                # ─────────────────────────────────────────────
                # absolute 模式时间戳调整
                # ─────────────────────────────────────────────
                # 本文件中每一行的时间戳都是从0开始的绝对秒数，
                # 需要加上偏移量使其接续前文件的末尾时间。
                #
                # 计算公式：
                #   offset = 前文件末尾时间 + gap - 本文件首帧时间
                #   新时间戳 = 原始时间戳 + offset
                #
                # 效果：
                #   本文件首帧调整后 = 前文件末尾时间 + gap
                #   本文件末帧调整后 = 前文件末尾时间 + gap + (末帧 - 首帧)
                #
                if af.first_ts is not None:
                    gap = 0.000001  # 1微秒间隔，避免与前文件末帧时间戳完全相同
                    offset = cumulative_offset + gap - af.first_ts
                else:
                    # 文件无消息（只有header），偏移量为0
                    offset = cumulative_offset

                # 对每一行消息调整时间戳
                for line in af.body_lines:
                    ts = extract_first_timestamp(line)
                    if ts is not None:
                        # 加上偏移量，得到接续前文件的新时间戳
                        new_ts = ts + offset
                        line = replace_timestamp(line, new_ts)
                    output_lines.append(line)

                # 更新累计偏移量：本文件调整后最末一行的时间戳
                if af.last_ts is not None:
                    cumulative_offset = af.last_ts + offset
            else:
                # ─────────────────────────────────────────────
                # relative 模式时间戳调整
                # ─────────────────────────────────────────────
                # 在 relative 模式下，每行的时间戳表示与上一事件的时间差（delta），
                # 例如：
                #   0.001000  → 距上一事件过了 0.001 秒
                #   0.000500  → 距上一事件过了 0.0005 秒
                #
                # 合并时需将 relative delta 累加转换为绝对时间戳：
                #   running_ts = 上一文件末尾绝对时间（cumulative_offset）
                #   对于每行: running_ts += 本行 delta
                #
                # 这样输出的时间戳变为绝对模式，确保时间轴连续。
                #
                running_ts = cumulative_offset
                for line in af.body_lines:
                    ts = extract_first_timestamp(line)
                    if ts is not None:
                        # ts 是 delta，累加得到绝对时间戳
                        running_ts += ts
                        line = replace_timestamp(line, running_ts)
                    output_lines.append(line)
                # 更新累计偏移量为最后一行的绝对时间戳
                cumulative_offset = running_ts

    # ══════════════════════════════════════════════════════════════════
    # 第6步：写入输出文件
    # ══════════════════════════════════════════════════════════════════
    # 确保输出目录存在（若指定了子目录路径，则自动创建）
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(output_lines)

    print(f"\n合并完成！输出文件: {output_file}")
    print(f"总行数: {len(output_lines)}")


def main():
    """
    命令行入口函数。

    解析命令行参数并调用 merge_asc_files 执行合并操作。

    支持的命令行参数:
        input_dir    : 必填，包含分段ASC文件的目录
        output_file  : 可选，输出文件路径（默认: merged_output.asc）
        --sort-by    : 可选，文件排序方式（默认: time）

    用法示例:
        python merge_asc_logs.py ./asc_logs
        python merge_asc_logs.py ./asc_logs combined.asc --sort-by name
    """
    # ── 构建命令行参数解析器 ──
    parser = argparse.ArgumentParser(
        description="拼接Kvaser分段ASC CAN log文件，避免时间戳错位"
    )
    # 第1个位置参数：输入目录（必填）
    parser.add_argument(
        "input_dir",
        help="包含分段ASC文件的目录",
    )
    # 第2个位置参数：输出文件路径（可选，默认值 merged_output.asc）
    parser.add_argument(
        "output_file",
        nargs="?",            # 0或1个参数，即此参数可选
        default="merged_output.asc",
        help="输出文件路径（默认: merged_output.asc）",
    )
    # 可选参数：文件排序方式
    parser.add_argument(
        "--sort-by",
        choices=["name", "time"],  # 只允许这两个值
        default="time",            # 默认按时间排序
        help="文件排序方式: name=按文件名, time=按header起始时间（默认: time）",
    )
    args = parser.parse_args()

    # ── 输入目录有效性检查 ──
    if not os.path.isdir(args.input_dir):
        print(f"错误: 目录 '{args.input_dir}' 不存在", file=sys.stderr)
        sys.exit(1)

    merge_asc_files(args.input_dir, args.output_file, args.sort_by)


if __name__ == "__main__":
    main()
