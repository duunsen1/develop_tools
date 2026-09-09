#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
viewer.py — 解析指纹 TP 差分数据 (fdd / txt)，供原生 Qt 可视化 & 导出 HTML 复用。

从脚本 focal_tp_diff_viewer.py 移植解析/打包/HTML 生成逻辑，无新增第三方依赖。
差异说明:
  * load() / parse_txt() 额外返回 (tx, rx)，支持 txt 头部自定义 Tx:/Rx:（fdd 固定 18×40）。
  * parse_txt() 帧切片长度用 main_n + 2*(tx+rx)（标准 18×40 下 = 836），不再写死。
  * 新增 parse_file() 顶层函数：返回可直接用于 widget 原生渲染的结构化 dict。
"""

import argparse  # noqa: F401  (保留脚本参数风格，本模块不强制使用)
import base64
import json
import os
import struct
from datetime import datetime

FRAME_VALS = 836            # 每帧值数: 720 主矩阵 + 40 + 18 + 40 + 18
RECORD_SIZE = 2618          # fdd 每条记录字节数
FDD_DATA_OFFSET = 0xA0      # fdd 数据区相对记录起始的字节偏移
FDD_RAW_VALS = 1229         # fdd 数据区 int16 数量
DEFAULT_TX = 18
DEFAULT_RX = 40
DEFAULT_FIRST_TH = 330      # 首点阈值（用于报点率统计/绿标）
DEFAULT_REPORT_TH = 240     # 报点阈值（黄标）


def format_android_time(ms):
    """将绝对时间戳(ms, epoch)格式化为 Android 风格墙钟时间 yyyy-MM-dd HH:mm:ss.SSS。

    绝对值过小（非真实 epoch，如纯递增帧号）时原样返回，避免展示成 1970。"""
    if ms is None or ms <= 0:
        return "-"
    try:
        # 小于 2001 年 epoch 大致阈值，视为非墙钟，不格式化
        if ms < 978307200000:
            return "-"
        dt = datetime.fromtimestamp(ms / 1000.0)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    except (OverflowError, OSError, ValueError):
        return "-"


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------
def parse_fdd(path):
    """解析 .fdd 二进制，返回 (timestamps_ms, frames, tx, rx)。

    frames 是 (N, 836) 的 int 列表，每帧 = [main720, perRx1, perTx1, perRx2, perTx2]。"""
    with open(path, 'rb') as f:
        data = f.read()
    n = len(data)
    if n % RECORD_SIZE != 0:
        print("WARNING: %d 字节不是 %d 的整数倍，按整除部分解析" % (n, RECORD_SIZE))
    n_rec = n // RECORD_SIZE
    frames, timestamps = [], []
    for i in range(n_rec):
        off = i * RECORD_SIZE
        ts_us = struct.unpack_from('<Q', data, off + 8)[0]
        vals = struct.unpack_from('>%dh' % FDD_RAW_VALS, data, off + FDD_DATA_OFFSET)
        frame = vals[1:1 + FRAME_VALS]      # 跳过数据区 idx0 计数器
        if len(frame) < FRAME_VALS:
            continue
        timestamps.append(ts_us // 1000)
        frames.append(list(frame))
    return timestamps, frames, DEFAULT_TX, DEFAULT_RX


def parse_txt(path):
    """解析 .txt dump，返回 (timestamps_ms, frames, tx, rx)。"""
    with open(path) as f:
        lines = f.read().splitlines()

    headers = lines[0] if lines else ''
    m_tx = DEFAULT_TX
    m_rx = DEFAULT_RX
    # 解析 'Tx:18,Rx:40'
    for part in headers.split(','):
        if part.startswith('Tx:'):
            m_tx = int(part.split(':')[1])
        elif part.startswith('Rx:'):
            m_rx = int(part.split(':')[1])

    main_n = m_tx * m_rx
    # 帧长度 = 主矩阵 + 2 组 (perRx + perTx)
    expected = main_n + 2 * (m_tx + m_rx)

    timestamps, frames = [], []
    cur_frame = None
    for line in lines[1:]:
        ls = line.strip()
        if not ls:
            continue
        if ls.startswith('Frame:'):
            if cur_frame is not None and len(cur_frame) >= expected:
                frames.append(cur_frame[:expected])
            ts = int(ls.split(',')[1].strip())
            timestamps.append(ts)
            cur_frame = []
        else:
            if cur_frame is None:
                continue
            for v in ls.split(','):
                if v.strip():
                    cur_frame.append(int(v.strip()))
    if cur_frame is not None and len(cur_frame) >= expected:
        frames.append(cur_frame[:expected])

    # 若帧数与时戳数不匹配，重新按值流切帧
    if len(frames) == 0 or len(frames) != len(timestamps):
        vals, timestamps = [], []
        cur = None
        for line in lines[1:]:
            ls = line.strip()
            if ls.startswith('Frame:'):
                if cur is not None:
                    vals.extend(cur)
                timestamps.append(int(ls.split(',')[1].strip()))
                cur = []
            elif cur is not None:
                cur.extend([int(x) for x in ls.split(',') if x.strip()])
        if cur is not None:
            vals.extend(cur)
        frames = [vals[i:i + expected] for i in range(0, len(vals) - expected + 1, expected)]

    return timestamps, frames, m_tx, m_rx


def load(path):
    """自动区分 fdd / txt。返回 (timestamps_ms, frames, tx, rx)。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == '.fdd':
        ts, frames, tx, rx = parse_fdd(path)
    else:
        ts, frames, tx, rx = parse_txt(path)
    return ts, frames, tx, rx


def parse_file(path, first_th=DEFAULT_FIRST_TH):
    """解析单个文件为用于原生可视化的 dict（纯 Python，无 numpy 依赖）。

    返回:
      {
        'name': 显示名(文件名),
        'path': 原始路径,
        'tx': int, 'rx': int, 'main_n': int, 'frame_vals': int,
        'rel_ts': [ms, ...] 相对起始时间戳,
        'frames': [[v, ... *frame_vals], ...],
        'base_ts': 起始绝对时间戳,
        'peaks': [每帧主矩阵最大值, ...],
        'stats': {duration_s, std, report_rate, peak_max, peak_median, median_interval_ms},
      }
    """
    timestamps, frames, tx, rx = load(path)
    main_n = tx * rx
    base = timestamps[0] if timestamps else 0
    rel_ts = [t - base for t in timestamps]
    frame_vals = len(frames[0]) if frames else main_n + 2 * (tx + rx)

    # 每帧峰值（主矩阵最大值）
    peaks = [max(fr[0:main_n]) for fr in frames]

    # ---- 整体统计（纯 Python 兜底，numpy 不强制） ----
    allv = [v for fr in frames for v in fr[0:main_n]]
    if allv:
        m = sum(allv) / len(allv)
        std = (sum((v - m) ** 2 for v in allv) / len(allv)) ** 0.5
    else:
        std = 0.0

    n = len(frames)
    peak_max = int(max(peaks)) if peaks else 0
    peak_median = 0.0
    if peaks:
        s = sorted(peaks)
        lm = len(s) // 2
        peak_median = float(s[lm]) if len(s) % 2 else (s[lm - 1] + s[lm]) / 2
    report_rate = (sum(1 for p in peaks if p > first_th) / len(peaks)) * 100 if peaks else 0
    duration_s = rel_ts[-1] / 1000 if n > 1 else 0

    if n > 1:
        dts = sorted(rel_ts[i + 1] - rel_ts[i] for i in range(n - 1))
        median_interval_ms = round(dts[len(dts) // 2])
    else:
        median_interval_ms = 0

    stats = {
        'duration_s': round(duration_s, 2),
        'std': round(std, 2),
        'report_rate': round(report_rate, 1),
        'peak_max': peak_max,
        'peak_median': round(peak_median, 1),
        'median_interval_ms': median_interval_ms,
    }
    # Android 墙钟时间（每帧绝对时间格式化）
    android_times = [format_android_time(base + t) for t in rel_ts]
    start_time = android_times[0] if android_times else "-"
    return {
        'name': os.path.basename(path),
        'path': path,
        'tx': tx,
        'rx': rx,
        'main_n': main_n,
        'frame_vals': frame_vals,
        'rel_ts': rel_ts,
        'frames': frames,
        'base_ts': base,
        'peaks': peaks,
        'stats': stats,
        'android_times': android_times,
        'start_time': start_time,
    }


def peek_meta(path):
    """仅解析 meta（不保留整帧数据），供外部预览。返回 load 结果。"""
    return load(path)


# --------------------------------------------------------------------------
# 打包（供导出 HTML）
# --------------------------------------------------------------------------
def pack(path, tx=None, rx=None, first_th=DEFAULT_FIRST_TH):
    """返回 (meta, payload_b64, ts_b64)。payload 每帧 836 个大端 int16。

    meta 除基础信息外, 额外带整体统计:
      duration_s  总时长(秒)
      std         主矩阵(全部帧)标准差
      report_rate 单格峰值 > first_th (首点阈值) 的帧占比(%)
      peak_max    单格峰值上限
      peak_median 单格峰值中位数
      median_interval_ms 帧间隔中位数(ms)
    """
    timestamps, frames, dtx, drx = load(path)
    if tx is None:
        tx = dtx
    if rx is None:
        rx = drx
    n = len(frames)
    # 过滤长度不足的帧
    norm = [fr for fr in frames if len(fr) >= FRAME_VALS][:n]
    # 若因长度过滤导致数量变化，重新归一
    if len(norm) != n:
        n = len(norm)

    main_n = tx * rx
    base = timestamps[0] if timestamps else 0
    rel_ts = [t - base for t in timestamps[:n]]

    # 单格峰值 (主矩阵最大值) 每帧
    peaks = [max(fr[0:main_n]) for fr in norm]

    # ---- 整体统计 ----
    try:
        import numpy as np
        mains = np.array([fr[0:main_n] for fr in norm], dtype=np.int32)
        std = float(mains.std())
        peak_median = float(np.median(peaks)) if peaks else 0.0
    except Exception:
        allv = [v for fr in norm for v in fr[0:main_n]]
        if allv:
            m = sum(allv) / len(allv)
            std = (sum((v - m) ** 2 for v in allv) / len(allv)) ** 0.5
        else:
            std = 0.0
        s = sorted(peaks)
        if s:
            lm = len(s) // 2
            peak_median = float(s[lm]) if len(s) % 2 else (s[lm - 1] + s[lm]) / 2
        else:
            peak_median = 0.0

    peak_max = int(max(peaks)) if peaks else 0
    report_rate = (sum(1 for p in peaks if p > first_th) / len(peaks)) * 100 if peaks else 0
    duration_s = (timestamps[n - 1] - timestamps[0]) / 1000 if n > 1 else 0
    if n > 1:
        dts = sorted(timestamps[i + 1] - timestamps[i] for i in range(n - 1))
        median_interval_ms = round(dts[len(dts) // 2])
    else:
        median_interval_ms = 0

    # 打包 int16 大端
    payload = bytearray()
    for fr in norm:
        for v in fr:
            payload += struct.pack('>h', v)
    ts_bytes = b''.join(struct.pack('>i', t) for t in rel_ts)

    meta = {
        'n': n,
        'tx': tx,
        'rx': rx,
        'main_n': main_n,
        'frame_vals': FRAME_VALS,
        'base_ts': base,
        'peak_max': peak_max,
        'peak_median': round(peak_median, 1),
        'std': round(std, 2),
        'report_rate': round(report_rate, 1),
        'report_th': first_th,
        'duration_s': round(duration_s, 2),
        'median_interval_ms': median_interval_ms,
    }
    return meta, base64.b64encode(bytes(payload)).decode('ascii'), base64.b64encode(ts_bytes).decode('ascii')


# --------------------------------------------------------------------------
# HTML 模板（与脚本一致，供导出复用）
# --------------------------------------------------------------------------
HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TP Diff 逐帧浏览器</title>
<style>
:root{color-scheme:light}
*{box-sizing:border-box}
body{margin:0;padding:16px;background:#f1f5f9;color:#0f172a;font-family:-apple-system,'Segoe UI',Roboto,'Helvetica Neue',sans-serif}
.hdr{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:14px}
.title{font-size:18px;font-weight:700}
.sub{font-size:12px;color:#64748b}
.controls{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.overview{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:14px}
@media(max-width:900px){.overview{grid-template-columns:repeat(3,1fr)}}
.ov{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:8px 16px;min-width:110px;text-align:left}
.ov .k{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.02em;margin-bottom:2px}
.ov .v{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums}
button{background:#fff;border:1px solid #cbd5e1;border-radius:8px;padding:7px 14px;font-size:14px;cursor:pointer}
button:hover{background:#f8fafc}
button.primary{background:#2563eb;color:#fff;border-color:#2563eb}
input[type=number],select{background:#fff;border:1px solid #cbd5e1;border-radius:8px;padding:8px 10px;font-size:15px;width:112px;text-align:center;font-variant-numeric:tabular-nums}
.layout{display:grid;grid-template-columns:1fr;gap:14px}
.panel{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:12px}
.panel h3{margin:0 0 8px;font-size:13px;color:#334155}
#heat{display:block;max-width:100%;height:auto;margin:8px auto;border:1px solid #e2e8f0;border-radius:6px}
canvas{display:block}
.framebar{display:flex;align-items:center;gap:8px;margin-top:8px;flex-wrap:wrap}
#fnum{font-size:16px;font-weight:700;min-width:70px}
#ftime{font-size:12px;color:#64748b}
#fslider{flex:1;min-width:120px}
.legend{display:flex;align-items:center;gap:6px;margin-top:8px;font-size:11px;color:#64748b}
.legend .bar{width:120px;height:10px;border-radius:5px;background:linear-gradient(90deg,#1d4ed8,#f8fafc,#ef4444)}
.stat-row{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px}
.stat{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:7px 9px}
.stat .k{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.03em}
.stat .v{font-size:17px;font-weight:700;margin-top:2px}
.tag{display:inline-block;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:600}
.tag.ok{background:#dcfce7;color:#15803d}
.tag.mid{background:#fef9c3;color:#a16207}
.tag.bad{background:#fee2e2;color:#b91c1c}
.proj-bar{background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:8px;margin-top:8px}
h4{margin:0 0 6px;font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.03em}
.peakchart{position:relative;height:130px;margin-top:10px}
.hint{font-size:11px;color:#94a3b8;margin-top:6px;line-height:1.5}
#pixreported{font-size:11px;color:#475569}
.slice{font-variant-numeric:tabular-nums}
</style>
</head>
<body>
<div class="hdr">
  <div>
    <div class="title">TP Diff 逐帧浏览器</div>
    <div class="sub" id="srcmeta">...</div>
  </div>
  <div class="controls">
    <button id="first">⏮ 首帧</button>
    <button id="prev">◀ 上一帧</button>
    <button id="play" class="primary">▶ 播放</button>
    <button id="next">下一帧 ▶</button>
    <button id="last">末帧 ⏭</button>
    <label style="font-size:14px;color:#475569">首点阈值
      <input type="number" id="th_first" value="330">
    </label>
    <label style="font-size:14px;color:#475569">报点阈值
      <input type="number" id="th_report" value="240">
    </label>
    <label style="font-size:14px;color:#475569">色标min
      <input type="number" id="xmin" value="-100">
    </label>
    <label style="font-size:14px;color:#475569">色标max
      <input type="number" id="xmax" value="300">
    </label>
  </div>
</div>

<div class="overview">
  <div class="ov"><div class="k">帧数</div><div class="v" id="ov_frames">-</div></div>
  <div class="ov"><div class="k">时长</div><div class="v" id="ov_dur">-</div></div>
  <div class="ov"><div class="k">主矩阵STD</div><div class="v" id="ov_std">-</div></div>
  <div class="ov"><div class="k">报点率(&gt;330)</div><div class="v" id="ov_rep">-</div></div>
  <div class="ov"><div class="k">峰值上限</div><div class="v" id="ov_pmax">-</div></div>
  <div class="ov"><div class="k">峰值中位</div><div class="v" id="ov_pmed">-</div></div>
</div>

<div class="layout">
  <!-- 上：投影 + 峰值曲线 -->
  <div class="panel">
    <h3>投影 &amp; 峰值曲线</h3>
    <div class="proj-bar">
      <h4>per-Rx 投影 (40)</h4>
      <canvas id="projrx" width="820" height="60"></canvas>
    </div>
    <div class="proj-bar">
      <h4>per-Tx 投影 (18)</h4>
      <canvas id="projtx" width="820" height="60"></canvas>
    </div>
    <div class="peakchart"><canvas id="peakchart"></canvas></div>
    <div class="hint" id="pixreported">峰值曲线，红/黄/绿分段对应报点状态，点击跳转。</div>
  </div>

  <!-- 下：热力图 + 帧控制 -->
  <div class="panel">
    <h3>主矩阵 18 × 40 热力图</h3>
    <canvas id="heat" width="410" height="180"></canvas>
    <div class="legend" style="justify-content:center"><span class="slice" id="cmin">-100</span><div class="bar"></div><span class="slice" id="cmax">300</span></div>
    <div class="framebar">
      <span id="fnum">0 / 0</span>
      <span id="ftime">t = 0 s</span>
      <input type="range" id="fslider" min="0" value="0" step="1">
    </div>
    <div class="stat-row">
      <div class="stat"><div class="k">峰值 max</div><div class="v" id="st_peak">-</div></div>
      <div class="stat"><div class="k">|Σ|</div><div class="v" id="st_abs">-</div></div>
      <div class="stat"><div class="k">报点</div><div class="v"><span id="st_tag" class="tag bad">-</span></div></div>
    </div>
    <div class="hint">鼠标滚轮 或 ←/→ 翻帧 · 空格播放 · 拖动滑块跳帧。峰值&gt;首点阈值 = 绿(可靠报点)；240~330 = 黄(勉强报点)；&lt;240 = 红(无法报点)。</div>
  </div>
</div>

<script>
const META = @@META@@;
const PAYLOAD = "@@PAYLOAD@@";
const TSPACK = "@@TSPACK@@";

const TX = META.tx, RX = META.rx, MAIN_N = META.main_n;
const FRAME_VALS = META.frame_vals;

// ---- 解码 base64 -> int16 大端 ----
function b64ToBytes(b64){
  const bin = atob(b64);
  const buf = new Uint8Array(bin.length);
  for(let i=0;i<bin.length;i++) buf[i] = bin.charCodeAt(i);
  return buf;
}
const frameBytes = b64ToBytes(PAYLOAD);
const tsBytes = b64ToBytes(TSPACK);
function int16be(buf, off){
  return (buf[off] << 8) | buf[off+1];
}
function int32be(buf, off){
  return (buf[off]<<24) | (buf[off+1]<<16) | (buf[off+2]<<8) | buf[off+3];
}
const N = META.n;
// 预取每帧 [0..835], 帧 i 位于 frameBytes 起始 i*FRAME_VALS*2
const frames = new Array(N);
const relTs = new Array(N);
for(let i=0;i<N;i++){
  const base = i*FRAME_VALS*2;
  const fr = new Int16Array(FRAME_VALS);
  for(let j=0;j<FRAME_VALS;j++) fr[j] = int16be(frameBytes, base + j*2);
  frames[i] = fr;
  relTs[i] = i===0 ? 0 : int32be(tsBytes, i*4);
}

// ---- 状态 ----
let idx = 0;
let playing = false;
let playTimer = null;
const heat = document.getElementById('heat');
const hctx = heat.getContext('2d');
// 计算热力图 canvas 尺寸 (按格子划分, 40列x18行)
const CELL_W = heat.width / RX;
const CELL_H = heat.height / TX;

function threshold(){
  return {
    first: parseFloat(document.getElementById('th_first').value) || 330,
    report: parseFloat(document.getElementById('th_report').value) || 240,
    xmin: parseFloat(document.getElementById('xmin').value) || -100,
    xmax: parseFloat(document.getElementById('xmax').value) || 300,
  };
}

function heatColor(v, xmin, xmax){
  let t = (v - xmin) / (xmax - xmin);
  t = Math.max(0, Math.min(1, t));
  let r,g,b;
  if(t < 0.5){
    const u = t*2;
    r = Math.round(29 + (249-29)*u);
    g = Math.round(78 + (250-78)*u);
    b = Math.round(216 + (250-216)*u);
  } else {
    const u = (t-0.5)*2;
    r = Math.round(249 + (239-249)*u);
    g = Math.round(250 + (68-250)*u);
    b = Math.round(250 + (68-250)*u);
  }
  return `rgb(${r},${g},${b})`;
}

// ---- 渲染热力图 (主矩阵) ----
function drawHeat(){
  const th = threshold();
  const fr = frames[idx];
  const main = fr; // [0..MAIN_N-1]
  for(let r=0;r<TX;r++){
    for(let c=0;c<RX;c++){
      const v = main[r*RX + c];
      hctx.fillStyle = heatColor(v, th.xmin, th.xmax);
      hctx.fillRect(c*CELL_W, r*CELL_H, CELL_W, CELL_H);
      // 超阈值描边
      if(v > th.first){ hctx.strokeStyle = '#16a34a'; hctx.lineWidth = 2; hctx.strokeRect(c*CELL_W+1, r*CELL_H+1, CELL_W-2, CELL_H-2); }
      else if(v > th.report){ hctx.strokeStyle = '#eab308'; hctx.lineWidth = 1; hctx.strokeRect(c*CELL_W+0.5, r*CELL_H+0.5, CELL_W-1, CELL_H-1); }
    }
  }
  // 网格线
  hctx.strokeStyle = 'rgba(148,163,184,.25)';
  hctx.lineWidth = 1;
  for(let c=0;c<=RX;c++){ hctx.beginPath(); hctx.moveTo(c*CELL_W,0); hctx.lineTo(c*CELL_W,heat.height); hctx.stroke(); }
  for(let r=0;r<=TX;r++){ hctx.beginPath(); hctx.moveTo(0,r*CELL_H); hctx.lineTo(heat.width,r*CELL_H); hctx.stroke(); }
  // 行列标注
  hctx.fillStyle = '#94a3b8';
  hctx.font = '10px sans-serif';
  hctx.fillText('Rx→', 2, 10);
  document.getElementById('cmin').textContent = Math.round(th.xmin);
  document.getElementById('cmax').textContent = Math.round(th.xmax);
}

// ---- 投影条 ----
function drawProj(){
  const fr = frames[idx];
  const main = fr;
  // per-Rx: 每列和 (第2段 perRx1 = fr[MAIN_N..MAIN_N+39])
  const pRx = fr.slice(MAIN_N, MAIN_N+40);
  const pTx = fr.slice(MAIN_N+40, MAIN_N+40+18);
  const cRx = document.getElementById('projrx'); const ctxR = cRx.getContext('2d');
  const cTx = document.getElementById('projtx'); const ctxT = cTx.getContext('2d');
  drawBars(ctxR, cRx, pRx, RX, '#2563eb');
  drawBars(ctxT, cTx, pTx, TX, '#059669');
}
function drawBars(ctx, cv, vals, n, color){
  ctx.clearRect(0,0,cv.width,cv.height);
  const bw = cv.width / n;
  // find norm
  let mx = 1;
  for(const v of vals) if(Math.abs(v)>mx) mx = Math.abs(v);
  for(let i=0;i<n;i++){
    const h = (vals[i]/mx) * (cv.height-10);
    ctx.fillStyle = color;
    ctx.fillRect(i*bw+1, cv.height-4-h, bw-2, h);
    ctx.strokeStyle = '#e2e8f0';
    ctx.strokeRect(i*bw+1, cv.height-4-h, bw-2, h);
  }
}

// ---- 峰值曲线 ----
function drawPeakChart(){
  const cv = document.getElementById('peakchart');
  const ctx = cv.getContext('2d');
  const w = cv.width = cv.parentElement.clientWidth;
  const h = cv.height = 130;
  ctx.clearRect(0,0,w,h);
  const th = threshold();
  // peaks (主矩阵最大值) 每帧
  const peaks = new Array(N);
  for(let i=0;i<N;i++){ let m=-32768; const fr=frames[i]; for(let j=0;j<MAIN_N;j++) if(fr[j]>m)m=fr[j]; peaks[i]=m; }
  // 绘区间背景
  function plotColor(v){
    if(v > th.first) return 'rgba(22,163,74,.35)';
    if(v > th.report) return 'rgba(234,179,8,.35)';
    return 'rgba(220,38,38,.35)';
  }
  const xmax = N>1? N-1 : 1;
  const ymin = Math.min(th.report-60, ...peaks);
  const ymax = Math.max(th.first+40, ...peaks);
  const X = i => (i/xmax)*(w-20)+10;
  const Y = v => h - ((v-ymin)/(ymax-ymin))*(h-16) - 4;
  // threshold lines
  ctx.setLineDash([4,3]);
  ctx.strokeStyle = '#16a34a'; ctx.beginPath(); ctx.moveTo(0,Y(th.first)); ctx.lineTo(w,Y(th.first)); ctx.stroke();
  ctx.strokeStyle = '#dc2626'; ctx.beginPath(); ctx.moveTo(0,Y(th.report)); ctx.lineTo(w,Y(th.report)); ctx.stroke();
  ctx.setLineDash([]);
  ctx.font = '10px sans-serif'; ctx.fillStyle = '#64748b';
  ctx.fillText('首点'+Math.round(th.first), w-70, Y(th.first)-3);
  ctx.fillText('报点'+Math.round(th.report), w-70, Y(th.report)-3);
  // line
  ctx.strokeStyle = '#0f172a'; ctx.lineWidth = 1.2; ctx.beginPath();
  for(let i=0;i<N;i++){ const x=X(i), y=Y(peaks[i]); if(i===0)ctx.moveTo(x,y); else ctx.lineTo(x,y); }
  ctx.stroke();
  // 当前帧指针
  ctx.strokeStyle = '#2563eb'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(X(idx),4); ctx.lineTo(X(idx),h-6); ctx.stroke();
}

// ---- 帧信息 ----
function fmtDate(ms){
  if(!ms || ms < 978307200000) return '-';
  const d = new Date(ms);
  if(isNaN(d.getTime())) return '-';
  const p = n => String(n).padStart(2,'0');
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ` +
         `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.` +
         String(d.getMilliseconds()).padStart(3,'0');
}

function updateInfo(){
  const fr = frames[idx];
  const th = threshold();
  let peak=-32768, abs=0;
  for(let j=0;j<MAIN_N;j++){ const v=fr[j]; if(v>peak)peak=v; abs+=Math.abs(v); }
  document.getElementById('fnum').textContent = `${idx + 1} / ${N}`;
  document.getElementById('ftime').textContent = `t = ${(relTs[idx]/1000).toFixed(2)} s · ${fmtDate(META.base_ts + relTs[idx])}`;
  document.getElementById('st_peak').textContent = peak;
  document.getElementById('st_abs').textContent = Math.round(abs);
  const tag = document.getElementById('st_tag');
  if(peak > th.first){ tag.textContent='可靠报点'; tag.className='tag ok'; }
  else if(peak > th.report){ tag.textContent='勉强报点'; tag.className='tag mid'; }
  else { tag.textContent='无法报点'; tag.className='tag bad'; }
  const slider = document.getElementById('fslider');
  slider.value = idx;
  document.getElementById('srcmeta').textContent =
    `来源: ${META.name} · ${TX}×${RX} · 帧间隔中位 ${META.median_interval_ms} ms · 报点率按首点阈值 ${META.report_th} 计算`;
}

// ---- 整体统计 (不随帧变, 初始化一次) ----
function fillOverview(){
  document.getElementById('ov_frames').textContent = META.n;
  document.getElementById('ov_dur').textContent = META.duration_s.toFixed(2) + ' s';
  document.getElementById('ov_std').textContent = META.std;
  document.getElementById('ov_rep').textContent = META.report_rate + '%';
  document.getElementById('ov_pmax').textContent = META.peak_max;
  document.getElementById('ov_pmed').textContent = META.peak_median;
}

function render(){ drawHeat(); drawProj(); drawPeakChart(); updateInfo(); }

function goto(i){ idx = Math.max(0, Math.min(N-1, i)); render(); }

// ---- 控制 ----
document.getElementById('prev').onclick = ()=>goto(idx-1);
document.getElementById('next').onclick = ()=>goto(idx+1);
document.getElementById('first').onclick = ()=>goto(0);
document.getElementById('last').onclick = ()=>goto(N-1);
document.getElementById('fslider').oninput = e=>goto(parseInt(e.target.value));
document.getElementById('play').onclick = ()=>{
  playing = !playing;
  document.getElementById('play').textContent = playing ? '⏸ 暂停' : '▶ 播放';
  if(playing){
    playTimer = setInterval(()=>{ if(idx>=N-1){idx=0;} goto(idx+1); }, 60);
  } else if(playTimer){ clearInterval(playTimer); playTimer=null; }
};
// 滚轮翻帧 (输入框/滑块上不劫持)
document.addEventListener('wheel', e=>{
  const tag = e.target.tagName;
  if(tag==='INPUT' || tag==='SELECT' || tag==='TEXTAREA') return;
  goto(idx + (e.deltaY>0 ? 1 : -1));
  e.preventDefault();
}, {passive:false});
// 键盘
document.addEventListener('keydown', e=>{
  if(e.key==='ArrowRight') goto(idx+1);
  else if(e.key==='ArrowLeft') goto(idx-1);
  else if(e.key===' '){ e.preventDefault(); document.getElementById('play').click(); }
});
// 阈值 / 色标变化
['th_first','th_report','xmin','xmax'].forEach(id=>{
  document.getElementById(id).addEventListener('change', render);
});
// 峰值曲线点击跳转
document.getElementById('peakchart').addEventListener('click', e=>{
  const cv = document.getElementById('peakchart');
  const x = e.offsetX / cv.clientWidth;
  goto(Math.round(x*(N-1)));
});

// init
document.getElementById('fslider').max = N-1;   // 滑块范围 = 总帧数(0..N-1)
document.getElementById('fslider').min = 0;
fillOverview();
window.addEventListener('resize', ()=>{ drawHeat(); drawProj(); drawPeakChart(); });
render();
</script>
</body>
</html>
'''


def build_viewer_html(meta, payload_b64, ts_b64):
    """用已打包的 base64 数据填充 HTML 模板，返回完整 HTML 字符串。"""
    return (HTML
            .replace('@@META@@', json.dumps(meta, ensure_ascii=False))
            .replace('@@PAYLOAD@@', payload_b64)
            .replace('@@TSPACK@@', ts_b64))


def export_html(data_path, out_path=None, first_th=DEFAULT_FIRST_TH):
    """对单个数据文件生成脚本同款独立 HTML，返回 (out_path, meta)。"""
    meta, payload, ts = pack(data_path, first_th=first_th)
    meta['name'] = os.path.basename(data_path)
    html = build_viewer_html(meta, payload, ts)
    if not out_path:
        out_path = os.path.splitext(data_path)[0] + '.viewer.html'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return out_path, meta
