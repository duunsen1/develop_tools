#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TP Diff 逐帧查看 - 原生 PySide6 可视化工具界面。

解析指纹 TP 差分数据 (.fdd / .txt) 为逐帧数据，用原生 QPainter 绘制：
  * 18×40 主矩阵热力图
  * per-Rx / per-Tx 投影条
  * 峰值曲线（点击跳帧）
支持同时加载多个解析结果，每个结果一个页签。
另可导出脚本同款独立 HTML（浏览器打开）。
"""

import os
import logging
import traceback

from PySide6.QtCore import Qt, QEvent, Signal, QThread, QTimer, QRectF, QPointF, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QListWidget, QListWidgetItem, QTabWidget, QSpinBox,
    QSlider, QGroupBox, QMessageBox, QScrollArea, QProgressBar,
    QAbstractItemView, QSizePolicy, QFrame,
)

from ...base_tool_widget import BaseToolWidget
from . import viewer

logger = logging.getLogger("devtools")

DEFAULT_FIRST = 330
DEFAULT_REPORT = 240
DEFAULT_XMIN = -100
DEFAULT_XMAX = 300


# --------------------------------------------------------------------------
# 颜色（复刻脚本 heatColor）
# --------------------------------------------------------------------------
def heat_color(v, xmin, xmax):
    """-100..300 线性色标：低->蓝，中->白，高->红。返回 QColor。"""
    if xmax == xmin:
        t = 0.0
    else:
        t = (v - xmin) / (xmax - xmin)
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        u = t * 2
        r = 29 + (249 - 29) * u
        g = 78 + (250 - 78) * u
        b = 216 + (250 - 216) * u
    else:
        u = (t - 0.5) * 2
        r = 249 + (239 - 249) * u
        g = 250 + (68 - 250) * u
        b = 250 + (68 - 250) * u
    return QColor(int(r), int(g), int(b))


# --------------------------------------------------------------------------
# 主矩阵热力图
# --------------------------------------------------------------------------
class HeatmapWidget(QWidget):
    """tx×rx 主矩阵热力图，色标 + 首点/报点阈值描边 + 网格。滚轮翻帧。"""

    frameDelta = Signal(int)

    def __init__(self, tx, rx, parent=None):
        super().__init__(parent)
        self._tx = tx
        self._rx = rx
        self._main_n = tx * rx
        self._frame = []
        self._xmin = DEFAULT_XMIN
        self._xmax = DEFAULT_XMAX
        self._first = DEFAULT_FIRST
        self._report = DEFAULT_REPORT
        self.setMinimumSize(480, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("""
            HeatmapWidget { background-color: #fff; border: 1px solid #e2e8f0; border-radius: 6px; }
        """)

    def set_frame(self, frame):
        self._frame = frame or []
        self.update()

    def set_scale(self, xmin, xmax):
        self._xmin = xmin
        self._xmax = xmax
        self.update()

    def set_thresholds(self, first, report):
        self._first = first
        self._report = report
        self.update()

    def sizeHint(self):
        return QSize(self._rx * 12, self._tx * 14)

    def wheelEvent(self, event):
        self.frameDelta.emit(1 if event.angleDelta().y() < 0 else -1)
        event.accept()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        w = self.width()
        h = self.height()
        if w <= 1 or h <= 1:
            return
        cellW = w / self._rx
        cellH = h / self._tx
        frame = self._frame
        for r in range(self._tx):
            for c in range(self._rx):
                i = r * self._rx + c
                v = frame[i] if i < len(frame) else 0
                p.fillRect(QRectF(c * cellW, r * cellH, cellW + 0.5, cellH + 0.5),
                           heat_color(v, self._xmin, self._xmax))
                if v > self._first:
                    p.setPen(QPen(QColor('#16a34a'), 2))
                    p.drawRect(QRectF(c * cellW + 1, r * cellH + 1, cellW - 2, cellH - 2))
                elif v > self._report:
                    p.setPen(QPen(QColor('#eab308'), 1))
                    p.drawRect(QRectF(c * cellW + 0.5, r * cellH + 0.5, cellW - 1, cellH - 1))
        # 网格线
        p.setPen(QPen(QColor(148, 163, 184, 63), 1))
        for c in range(self._rx + 1):
            x = c * cellW
            p.drawLine(QPointF(x, 0), QPointF(x, h))
        for r in range(self._tx + 1):
            y = r * cellH
            p.drawLine(QPointF(0, y), QPointF(w, y))
        # 标注
        p.setPen(QColor('#94a3b8'))
        p.setFont(QFont('sans-serif', 7))
        p.drawText(QRectF(2, 2, 44, 12), 'Rx→')


# --------------------------------------------------------------------------
# 投影条
# --------------------------------------------------------------------------
class ProjectionWidget(QWidget):
    """per-Rx / per-Tx 投影柱状条，按最大绝对值归一化。"""

    def __init__(self, count, color, parent=None):
        super().__init__(parent)
        self._count = count
        self._color = QColor(color)
        self._vals = []
        self.setFixedHeight(70)
        self.setMinimumWidth(200)
        self.setStyleSheet("""
            ProjectionWidget { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; }
        """)

    def set_vals(self, vals):
        self._vals = list(vals) if vals else []
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        w = self.width()
        h = self.height()
        n = self._count
        if n <= 0:
            return
        p.setPen(Qt.NoPen)
        p.setBrush(self._color)
        bw = w / n
        mx = 1
        for v in self._vals:
            if abs(v) > mx:
                mx = abs(v)
        base = h - 4
        for i in range(n):
            v = self._vals[i] if i < len(self._vals) else 0
            bh = abs(v) / mx * (h - 10)
            p.fillRect(QRectF(i * bw + 1, base - bh, bw - 2, bh), self._color)


# --------------------------------------------------------------------------
# 峰值曲线（点击跳帧）
# --------------------------------------------------------------------------
class PeakChartWidget(QWidget):
    """峰值曲线 + 首点/报点虚线阈值 + 当前帧竖线。"""

    frameSelected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._peaks = []
        self._first = DEFAULT_FIRST
        self._report = DEFAULT_REPORT
        self._current = 0
        self.setFixedHeight(150)
        self.setMinimumWidth(320)
        self.setStyleSheet("""
            PeakChartWidget { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; }
        """)

    def set_peaks(self, peaks):
        self._peaks = [int(p) for p in (peaks or [])]
        self.update()

    def set_params(self, first, report):
        self._first = first
        self._report = report
        self.update()

    def set_current(self, idx):
        self._current = idx
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width()
        h = self.height()
        peaks = self._peaks
        n = len(peaks)
        if n == 0:
            p.setPen(QColor('#94a3b8'))
            p.setFont(QFont('sans-serif', 9))
            p.drawText(self.rect(), Qt.AlignCenter, '无峰值数据')
            return
        ymin = min(self._report - 60, *peaks)
        ymax = max(self._first + 40, *peaks)
        if ymax <= ymin:
            ymax = ymin + 1

        def X(i):
            denom = (n - 1) if n > 1 else 1
            return (i / denom) * (w - 20) + 10

        def Y(v):
            return h - ((v - ymin) / (ymax - ymin)) * (h - 16) - 4

        # 阈值虚线
        p.setPen(QPen(QColor('#16a34a'), 1, Qt.DashLine))
        p.drawLine(QPointF(0, Y(self._first)), QPointF(w, Y(self._first)))
        p.setPen(QPen(QColor('#dc2626'), 1, Qt.DashLine))
        p.drawLine(QPointF(0, Y(self._report)), QPointF(w, Y(self._report)))
        p.setPen(QColor('#64748b'))
        p.setFont(QFont('sans-serif', 8))
        p.drawText(QPointF(w - 78, Y(self._first) - 3), '首点%.0f' % self._first)
        p.drawText(QPointF(w - 78, Y(self._report) - 3), '报点%.0f' % self._report)

        # 峰值折线
        p.setPen(QPen(QColor('#0f172a'), 1.2))
        prev = None
        for i in range(n):
            pt = QPointF(X(i), Y(peaks[i]))
            if prev is not None:
                p.drawLine(prev, pt)
            prev = pt

        # 当前帧指针
        x = X(self._current)
        p.setPen(QPen(QColor('#2563eb'), 2))
        p.drawLine(QPointF(x, 4), QPointF(x, h - 6))

    def mousePressEvent(self, event):
        n = len(self._peaks)
        if n == 0:
            return
        w = self.width()
        x = event.position().x()
        frac = (x - 10) / ((w - 20) or 1)
        idx = int(round(frac * (n - 1)))
        idx = max(0, min(n - 1, idx))
        self.frameSelected.emit(idx)


# --------------------------------------------------------------------------
# 单结果查看页（每个 tab 一个）
# --------------------------------------------------------------------------
class DiffViewerPage(QWidget):
    """一个解析结果的可视化页面，含独立帧状态/播放/阈值。"""

    def __init__(self, series: dict, parent=None, start_idx=0,
                 first=DEFAULT_FIRST, report=DEFAULT_REPORT,
                 xmin=DEFAULT_XMIN, xmax=DEFAULT_XMAX):
        super().__init__(parent)
        self._series = series
        self._frames = series['frames']
        self._rel_ts = series['rel_ts']
        self._tx = series['tx']
        self._rx = series['rx']
        self._main_n = series['main_n']
        self._frame_vals = series['frame_vals']
        self._peaks = series.get('peaks', [])
        self._n = len(self._frames)
        self._idx = 0
        self._playing = False
        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._on_tick)
        self._init_first = first
        self._init_report = report
        self._init_xmin = xmin
        self._init_xmax = xmax
        self._start_idx = start_idx
        self._fs_windows = []   # 保持全屏窗口引用，避免被 GC

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._content = QWidget()
        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll)

        self._build_ui()
        if self._n > 0:
            self._goto(max(0, min(self._start_idx, self._n - 1)))
            self._refresh_view()
        else:
            self._set_empty()

    # ---- UI ----
    def _build_ui(self):
        lay = QVBoxLayout(self._content)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)

        # 概览（与帧数/时长等卡片同一行对齐，导出 HTML 靠右）
        st = self._series.get('stats', {})
        cards = [
            ("起始时间", self._series.get('start_time', '-')),
            ("帧数", str(self._n)),
            ("时长", f"{st.get('duration_s', 0):.2f} s"),
            ("主矩阵STD", str(st.get('std', '-'))),
            ("报点率", f"{st.get('report_rate', 0)}%"),
            ("峰值上限", str(st.get('peak_max', '-'))),
            ("峰值中位", str(st.get('peak_median', '-'))),
        ]
        ov = QHBoxLayout()
        ov.setSpacing(8)
        for label, val in cards:
            ov.addWidget(self._card(label, val))
        ov.addStretch()
        self._btn_export = QPushButton("导出 HTML")
        self._btn_export.setToolTip("导出脚本同款独立 HTML，可用浏览器交互浏览")
        self._style_btn(self._btn_export, '#e67e22', '#ca6f1e')
        self._btn_export.clicked.connect(self._export_html)
        ov.addWidget(self._btn_export, 0, Qt.AlignVCenter)
        lay.addLayout(ov)

        # ---- 热力图区 ----
        heat_group = QGroupBox(f"主矩阵 {self._tx} × {self._rx} 热力图")
        heat_group.setStyleSheet(GROUP_STYLE)
        hl = QVBoxLayout(heat_group)

        self._heat = HeatmapWidget(self._tx, self._rx)
        self._heat.frameDelta.connect(lambda d: self._goto(self._idx + d))
        hl.addWidget(self._heat)

        # 色标 + 阈值行
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("色标min:"))
        self._sp_xmin = self._spin(self._init_xmin, -50000, 50000)
        self._sp_xmin.setSuffix("")
        ctrl.addWidget(self._sp_xmin)
        ctrl.addWidget(QLabel("色标max:"))
        self._sp_xmax = self._spin(self._init_xmax, -50000, 50000)
        ctrl.addWidget(self._sp_xmax)
        ctrl.addSpacing(18)
        ctrl.addWidget(QLabel("首点阈值:"))
        self._sp_first = self._spin(self._init_first, 0, 60000)
        ctrl.addWidget(self._sp_first)
        ctrl.addWidget(QLabel("报点阈值:"))
        self._sp_report = self._spin(self._init_report, 0, 60000)
        ctrl.addWidget(self._sp_report)
        ctrl.addStretch()
        hl.addLayout(ctrl)

        # 图例
        legend = QHBoxLayout()
        legend.addStretch()
        self._legend_min = QLabel(str(DEFAULT_XMIN))
        self._legend_min.setStyleSheet("font-size: 11px; color: #64748b;")
        legend.addWidget(self._legend_min)
        bar = QLabel()
        bar.setFixedSize(120, 10)
        bar.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #1d4ed8, stop:0.5 #f8fafc, stop:1 #ef4444); border-radius: 5px;")
        legend.addWidget(bar)
        self._legend_max = QLabel(str(DEFAULT_XMAX))
        self._legend_max.setStyleSheet("font-size: 11px; color: #64748b;")
        legend.addWidget(self._legend_max)
        legend.addStretch()
        hl.addLayout(legend)

        stat_row = QHBoxLayout()
        stat_row.setSpacing(8)
        self._st_peak = self._stat("峰值 max", "-")
        self._st_abs = self._stat("|Σ|", "-")
        self._st_tag = self._stat_tag()
        stat_row.addWidget(self._st_peak)
        stat_row.addWidget(self._st_abs)
        stat_row.addWidget(self._st_tag)
        stat_row.addStretch()
        hl.addLayout(stat_row)

        lay.addWidget(heat_group)

        # ---- 投影 + 峰值曲线 ----
        proj_group = QGroupBox("投影 & 峰值曲线")
        proj_group.setStyleSheet(GROUP_STYLE)
        pl = QVBoxLayout(proj_group)
        pl.addWidget(QLabel(f"per-Rx 投影 ({self._rx})"))
        self._proj_rx = ProjectionWidget(self._rx, '#2563eb')
        pl.addWidget(self._proj_rx)
        pl.addWidget(QLabel(f"per-Tx 投影 ({self._tx})"))
        self._proj_tx = ProjectionWidget(self._tx, '#059669')
        pl.addWidget(self._proj_tx)
        pl.addWidget(QLabel("峰值曲线（红/黄/绿分段对应报点状态，点击跳帧）"))
        self._peak = PeakChartWidget()
        self._peak.set_peaks(self._peaks)
        self._peak.frameSelected.connect(self._goto)
        pl.addWidget(self._peak)
        lay.addWidget(proj_group)

        # ---- 帧控制 ----
        fc = QHBoxLayout()
        fc.setSpacing(6)
        self._play_btn = None
        for text, slot, primary in (
            ("⏮ 首帧", lambda: self._goto(0), False),
            ("◀ 上一帧", lambda: self._goto(self._idx - 1), False),
            ("▶ 播放", self._toggle_play, True),
            ("下一帧 ▶", lambda: self._goto(self._idx + 1), False),
            ("末帧 ⏭", lambda: self._goto(self._n - 1), False),
        ):
            b = QPushButton(text)
            self._style_btn(b, '#3b82f6' if primary else '#ffffff',
                            '#2563eb' if primary else '#eef2f7')
            b.clicked.connect(slot)
            fc.addWidget(b)
            if primary:
                self._play_btn = b

        self._lbl_frame = QLabel("0 / 0")
        self._lbl_frame.setStyleSheet("font-size: 15px; font-weight: bold; min-width: 80px;")
        fc.addWidget(self._lbl_frame)
        self._lbl_time = QLabel("t = 0 s")
        self._lbl_time.setStyleSheet("font-size: 12px; color: #64748b; min-width: 90px;")
        fc.addWidget(self._lbl_time)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, max(0, self._n - 1))
        self._slider.setValue(0)
        self._slider.valueChanged.connect(lambda v: self._goto(v, from_slider=True))
        fc.addWidget(self._slider, 1)

        lay.addLayout(fc)

        # 阈值/色标变化 → 触发重绘
        for sp in (self._sp_first, self._sp_report, self._sp_xmin, self._sp_xmax):
            sp.valueChanged.connect(lambda _: self._refresh_view())

    # ---- 组件辅助 ----
    @staticmethod
    def _spin(value, lo, hi):
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(value)
        s.setStyleSheet("QSpinBox { padding: 3px 6px; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 13px; }")
        return s

    @staticmethod
    def _style_btn(btn, base, hover):
        btn.setStyleSheet(f"""
            QPushButton {{ background-color: {base}; color: #0f172a; border: 1px solid #cbd5e1;
                border-radius: 6px; padding: 6px 12px; font-size: 13px; font-weight: bold; }}
            QPushButton:hover {{ background-color: {hover}; }}
            QPushButton:disabled {{ background-color: #e2e8f0; color: #94a3b8; }}
        """)

    @staticmethod
    def _card(label, val):
        w = QWidget()
        w.setStyleSheet("""
            QWidget { background-color: #fff; border: 1px solid #e2e8f0; border-radius: 8px; }
        """)
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 6, 10, 6)
        k = QLabel(label)
        k.setStyleSheet("font-size: 10px; color: #64748b; border: none; text-transform: uppercase;")
        t = QLabel(val)
        t.setStyleSheet("font-size: 17px; font-weight: bold; color: #0f172a; border: none;")
        v.addWidget(k)
        v.addWidget(t)
        return w

    @staticmethod
    def _stat(label, val):
        w = QWidget()
        w.setStyleSheet("""
            QWidget { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }
        """)
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 6, 10, 6)
        k = QLabel(label)
        k.setStyleSheet("font-size: 10px; color: #64748b; border: none;")
        t = QLabel(val)
        t.setStyleSheet("font-size: 16px; font-weight: bold; border: none;")
        v.addWidget(k)
        v.addWidget(t)
        w._val_label = t
        return w

    def _stat_tag(self):
        w = QWidget()
        w.setStyleSheet("""
            QWidget { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }
        """)
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 6, 10, 6)
        k = QLabel("报点")
        k.setStyleSheet("font-size: 10px; color: #64748b; border: none;")
        t = QLabel("无法报点")
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("font-size: 14px; font-weight: bold; border-radius: 4px; padding: 2px 8px; background-color: #fee2e2; color: #b91c1c;")
        v.addWidget(k)
        v.addWidget(t)
        w._tag_label = t
        return w

    # ---- 阈值 ----
    def _th(self):
        return {
            'first': self._sp_first.value(),
            'report': self._sp_report.value(),
            'xmin': self._sp_xmin.value(),
            'xmax': self._sp_xmax.value(),
        }

    # ---- 渲染 ----
    def _refresh_view(self):
        th = self._th()
        self._heat.set_thresholds(th['first'], th['report'])
        self._heat.set_scale(th['xmin'], th['xmax'])
        self._peak.set_params(th['first'], th['report'])
        self._legend_min.setText(str(th['xmin']))
        self._legend_max.setText(str(th['xmax']))
        self._update_stats()
        self._heat.update()
        self._peak.update()

    def _render_frame(self):
        if self._n == 0:
            return
        fr = self._frames[self._idx]
        main_n = self._main_n
        self._heat.set_frame(fr)
        self._proj_rx.set_vals(fr[main_n:main_n + self._rx])
        self._proj_tx.set_vals(fr[main_n + self._rx:main_n + self._rx + self._tx])
        self._peak.set_current(self._idx)
        self._lbl_frame.setText(f"{self._idx + 1} / {self._n}")
        atime = (self._series.get('android_times') or [])
        timestr = f"t = {self._rel_ts[self._idx] / 1000:.2f} s"
        if self._idx < len(atime):
            timestr += f" · {atime[self._idx]}"
        self._lbl_time.setText(timestr)
        self._slider.blockSignals(True)
        self._slider.setValue(self._idx)
        self._slider.blockSignals(False)
        self._update_stats()

    def _update_stats(self):
        if self._n == 0:
            return
        fr = self._frames[self._idx]
        peak = max(fr[:self._main_n])
        abl = sum(abs(v) for v in fr[:self._main_n])
        self._st_peak._val_label.setText(str(peak))
        self._st_abs._val_label.setText(str(round(abl)))
        th = self._th()
        tag = self._st_tag._tag_label
        if peak > th['first']:
            tag.setText("可靠报点")
            tag.setStyleSheet("font-size: 14px; font-weight: bold; border-radius: 4px; padding: 2px 8px; background-color: #dcfce7; color: #15803d;")
        elif peak > th['report']:
            tag.setText("勉强报点")
            tag.setStyleSheet("font-size: 14px; font-weight: bold; border-radius: 4px; padding: 2px 8px; background-color: #fef9c3; color: #a16207;")
        else:
            tag.setText("无法报点")
            tag.setStyleSheet("font-size: 14px; font-weight: bold; border-radius: 4px; padding: 2px 8px; background-color: #fee2e2; color: #b91c1c;")

    def _set_empty(self):
        self._heat.set_frame([])
        self._st_peak._val_label.setText("-")
        self._st_abs._val_label.setText("-")
        self._st_tag._tag_label.setText("无效")
        self._lbl_frame.setText("0 / 0")

    # ---- 导航 ----
    def _goto(self, i, from_slider=False):
        if self._n == 0:
            return
        self._idx = max(0, min(self._n - 1, i))
        self._render_frame()

    def _toggle_play(self):
        if self._n == 0:
            return
        self._playing = not self._playing
        self._update_play_btn()
        if self._playing:
            self._timer.start()
        else:
            self._timer.stop()

    def _on_tick(self):
        nxt = (self._idx + 1) % self._n
        self._goto(nxt)

    def _update_play_btn(self):
        if self._play_btn is not None:
            self._play_btn.setText('⏸ 暂停' if self._playing else '▶ 播放')
            if self._playing:
                self._play_btn.setStyleSheet("""
                    QPushButton { background-color: #3b82f6; color: #fff; border: 1px solid #2563eb;
                        border-radius: 6px; padding: 6px 12px; font-size: 13px; font-weight: bold; }
                    QPushButton:hover { background-color: #2563eb; }
                """)
            else:
                self._style_btn(self._play_btn, '#3b82f6', '#2563eb')

    def _export_html(self):
        if self._n == 0:
            QMessageBox.warning(self, "提示", "当前数据无有效帧，无法导出")
            return
        default = os.path.splitext(self._series['path'])[0] + '.viewer.html'
        path, _ = QFileDialog.getSaveFileName(self, "导出 HTML 查看器", default,
                                              "HTML 文件 (*.html);;所有文件 (*.*)")
        if not path:
            return
        try:
            out, meta = viewer.export_html(self._series['path'], out_path=path)
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出 HTML 时出错:\n{e}")
            logger.error("TP diff 导出 HTML 失败: %s", e, exc_info=True)
            return
        QMessageBox.information(self, "导出成功", f"已生成：\n{out}\n\n{meta['n']} 帧，{meta['duration_s']}s")
        try:
            os.startfile(out)
        except Exception:
            pass

    def open_fullscreen(self):
        """用当前帧与阈值打开全屏预览窗口。"""
        if self._n == 0:
            QMessageBox.warning(self, "提示", "当前数据无有效帧，无法全屏预览")
            return
        th = self._th()
        win = FullscreenPreview(self._series, start_idx=self._idx,
                                first=th['first'], report=th['report'],
                                xmin=th['xmin'], xmax=th['xmax'])
        self._fs_windows.append(win)
        win.destroyed.connect(lambda _=None, w=win: self._forget_fs(w))

    def _forget_fs(self, win):
        if win in self._fs_windows:
            self._fs_windows.remove(win)


# --------------------------------------------------------------------------
# 全屏预览窗口（Esc 退出）
# --------------------------------------------------------------------------
class FullscreenPreview(QWidget):
    """宿主一个 DiffViewerPage 的顶层全屏窗口，按 Esc 退出。"""

    def __init__(self, series: dict, start_idx=0, first=DEFAULT_FIRST, report=DEFAULT_REPORT,
                 xmin=DEFAULT_XMIN, xmax=DEFAULT_XMAX):
        super().__init__(None, Qt.Window)
        self.setWindowTitle(f"全屏预览 - {series['name']}")
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._page = DiffViewerPage(series, start_idx=start_idx, first=first,
                                    report=report, xmin=xmin, xmax=xmax)
        outer.addWidget(self._page)
        self.installEventFilter(self)
        self.showFullScreen()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self.close()
            return True
        return super().eventFilter(obj, event)


# --------------------------------------------------------------------------
# 后台解析线程
# --------------------------------------------------------------------------
class ParseWorker(QThread):
    """后台逐个解析文件，避免大文件阻塞 UI。"""

    parsed = Signal(object)          # series dict
    file_error = Signal(str, str)    # 文件名, 错误
    progressed = Signal(int, int)    # 已处理, 总数
    finished = Signal(int, int)      # 成功, 失败

    def __init__(self, files, parent=None):
        super().__init__(parent)
        self._files = list(files)

    def run(self):
        ok = fail = 0
        for i, f in enumerate(self._files):
            try:
                series = viewer.parse_file(f)
                if not series['frames']:
                    raise ValueError("未解析到有效帧")
                self.parsed.emit(series)
                ok += 1
            except Exception as e:
                logger.warning("解析失败: %s (%s)", f, e)
                self.file_error.emit(os.path.basename(f), str(e))
                fail += 1
            self.progressed.emit(i + 1, len(self._files))
        self.finished.emit(ok, fail)


# --------------------------------------------------------------------------
# 支持拖拽的文件列表
# --------------------------------------------------------------------------
class DropListWidget(QListWidget):
    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setStyleSheet("""
            QListWidget {
                border: 2px dashed #BDC3C7; border-radius: 8px;
                background-color: #FAFAFA; padding: 10px; font-size: 13px;
            }
            QListWidget:focus { border-color: #3498DB; }
            QListWidget::item { padding: 6px 10px; border-radius: 4px; }
            QListWidget::item:selected { background-color: #3498DB; color: white; }
        """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        files = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path) and path.lower().endswith(('.fdd', '.txt')):
                files.append(path)
        if files:
            self.files_dropped.emit(files)


# --------------------------------------------------------------------------
# 主工具
# --------------------------------------------------------------------------
class TpDiffViewerWidget(BaseToolWidget):
    """指纹 TP Diff 逐帧查看工具。"""

    def tool_name(self) -> str:
        return "TP diff解析"

    def tool_tip(self) -> str:
        return "解析指纹 TP 差分数据 (.fdd/.txt)，逐帧查看热力图/投影/峰值，支持多结果"

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title = QLabel("指纹 TP Diff 逐帧查看")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #2C3E50;")
        layout.addWidget(title)

        desc = QLabel("选择指纹 TP 差分数据文件（.fdd 二进制 / .txt 文本 dump），解析后逐帧查看热力图、投影与峰值曲线。支持同时加载多个结果。")
        desc.setStyleSheet("font-size: 13px; color: #7F8C8D;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # ---- 文件选择 ----
        grp = QGroupBox("文件选择")
        grp.setStyleSheet(GROUP_STYLE)
        gv = QVBoxLayout(grp)

        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("添加文件")
        self._btn_add.setStyleSheet(BTN_PRIMARY)
        self._btn_add.clicked.connect(self._on_add_files)
        btn_row.addWidget(self._btn_add)

        self._btn_clear = QPushButton("清空")
        self._btn_clear.setStyleSheet(BTN_GRAY)
        self._btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(self._btn_clear)

        btn_row.addStretch()
        self._lbl_count = QLabel("已选择 0 个文件")
        self._lbl_count.setStyleSheet("font-size: 13px; color: #7F8C8D;")
        btn_row.addWidget(self._lbl_count)
        gv.addLayout(btn_row)

        self._file_list = DropListWidget()
        self._file_list.files_dropped.connect(self._on_files_dropped)
        self._file_list.setMinimumHeight(90)
        gv.addWidget(self._file_list)

        hint = QLabel("支持拖拽 .fdd / .txt 文件到上方区域")
        hint.setStyleSheet("font-size: 12px; color: #BDC3C7;")
        hint.setAlignment(Qt.AlignCenter)
        gv.addWidget(hint)

        layout.addWidget(grp)

        # ---- 解析按钮 + 进度 ----
        action_row = QHBoxLayout()
        self._btn_parse = QPushButton("开始解析")
        self._btn_parse.setStyleSheet(BTN_GREEN)
        self._btn_parse.clicked.connect(self._on_parse)
        self._btn_parse.setEnabled(False)
        action_row.addWidget(self._btn_parse)

        self._btn_fs_current = QPushButton("⛶ 全屏预览当前")
        self._btn_fs_current.setStyleSheet(BTN_PURPLE)
        self._btn_fs_current.setToolTip("全屏预览当前选中的结果（Esc 退出）")
        self._btn_fs_current.setEnabled(False)
        self._btn_fs_current.clicked.connect(self._on_fullscreen_current)
        action_row.addWidget(self._btn_fs_current)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(6)
        self._progress.setStyleSheet("""
            QProgressBar { border: none; background-color: #ECF0F1; border-radius: 3px; }
            QProgressBar::chunk { background-color: #3498DB; border-radius: 3px; }
        """)
        self._progress.hide()
        action_row.addWidget(self._progress, 1)

        self._lbl_progress = QLabel("")
        self._lbl_progress.setStyleSheet("font-size: 12px; color: #7F8C8D;")
        action_row.addWidget(self._lbl_progress)
        layout.addLayout(action_row)

        # ---- 结果 ----
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.currentChanged.connect(lambda _: self._update_fs_btn())
        self._tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #E0E0E0; border-radius: 6px; background-color: #fff; }
            QTabBar::tab { padding: 8px 16px; background: #ECF0F1; border: 1px solid #E0E0E0;
                border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; }
            QTabBar::tab:selected { background: #fff; }
        """)
        layout.addWidget(self._tabs, 1)

        self._main_layout.addLayout(layout)

        self._files = []
        self._parsed_paths = set()
        self._worker = None

    # ---- 文件管理 ----
    def _on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择 TP Diff 数据文件", "",
            "TP Diff 数据 (*.fdd *.txt);;所有文件 (*.*)"
        )
        if files:
            self._on_files_dropped(files)

    def _on_files_dropped(self, files):
        for f in files:
            if f not in self._files:
                self._files.append(f)
                item = QListWidgetItem(f)
                self._file_list.addItem(item)
        self._update_count()

    def _on_clear(self):
        self._files.clear()
        self._file_list.clear()
        self._update_count()
        self._parsed_paths.clear()
        while self._tabs.count():
            self._tabs.removeTab(0)

    def _update_count(self):
        self._lbl_count.setText(f"已选择 {len(self._files)} 个文件")
        self._btn_parse.setEnabled(len(self._files) > 0)

    def _close_tab(self, i):
        w = self._tabs.widget(i)
        if w is not None:
            self._tabs.removeTab(i)
            w.deleteLater()
        self._update_fs_btn()

    # ---- 解析 ----
    def _on_parse(self):
        if not self._files:
            QMessageBox.warning(self, "提示", "请先添加文件")
            return
        self._btn_parse.setEnabled(False)
        self._progress.show()
        self._lbl_progress.setText("解析中...")
        self._worker = ParseWorker(self._files)
        self._worker.parsed.connect(self._on_parsed)
        self._worker.file_error.connect(self._on_file_error)
        self._worker.progressed.connect(self._on_progressed)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_parsed(self, series: dict):
        if series['path'] in self._parsed_paths:
            return
        self._parsed_paths.add(series['path'])
        page = DiffViewerPage(series)
        idx = self._tabs.addTab(page, series['name'])
        self._tabs.setCurrentIndex(idx)
        self._update_fs_btn()

    def _update_fs_btn(self):
        page = self._tabs.currentWidget()
        self._btn_fs_current.setEnabled(isinstance(page, DiffViewerPage) and page._n > 0)

    def _on_fullscreen_current(self):
        page = self._tabs.currentWidget()
        if isinstance(page, DiffViewerPage):
            page.open_fullscreen()

    def _on_file_error(self, name, err):
        self._lbl_progress.setText(f"{name} 解析失败")

    def _on_progressed(self, i, n):
        self._lbl_progress.setText(f"解析中 {i}/{n}")

    def _on_finished(self, ok, fail):
        self._progress.hide()
        self._btn_parse.setEnabled(True)
        self._lbl_progress.setText(f"完成：成功 {ok}，失败 {fail}")
        if fail:
            QMessageBox.warning(self, "部分失败",
                                f"成功解析 {ok} 个，失败 {fail} 个。\n失败文件详情见日志。")

    def on_deactivate(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(1000)
        for i in range(self._tabs.count()):
            pg = self._tabs.widget(i)
            if isinstance(pg, DiffViewerPage):
                pg._timer.stop()


# --------------------------------------------------------------------------
# 共享样式
# --------------------------------------------------------------------------
GROUP_STYLE = """
    QGroupBox { font-size: 14px; font-weight: bold; color: #2C3E50;
        border: 1px solid #E0E0E0; border-radius: 8px; margin-top: 12px;
        padding: 15px 10px 10px 10px; }
    QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left;
        padding: 0 8px; background-color: #F5F6FA; }
"""

BTN_PRIMARY = """
    QPushButton { background-color: #3498DB; color: white; border: none;
        padding: 8px 20px; border-radius: 6px; font-size: 13px; font-weight: bold; }
    QPushButton:hover { background-color: #2980B9; }
    QPushButton:disabled { background-color: #BDC3C7; }
"""

BTN_GRAY = """
    QPushButton { background-color: #95A5A6; color: white; border: none;
        padding: 8px 20px; border-radius: 6px; font-size: 13px; }
    QPushButton:hover { background-color: #7F8C8D; }
    QPushButton:disabled { background-color: #BDC3C7; }
"""

BTN_GREEN = """
    QPushButton { background-color: #27AE60; color: white; border: none;
        padding: 10px 30px; border-radius: 6px; font-size: 14px; font-weight: bold; }
    QPushButton:hover { background-color: #219A52; }
    QPushButton:disabled { background-color: #BDC3C7; }
"""

BTN_PURPLE = """
    QPushButton { background-color: #8E44AD; color: white; border: none;
        padding: 10px 20px; border-radius: 6px; font-size: 13px; font-weight: bold; }
    QPushButton:hover { background-color: #7D3C98; }
    QPushButton:disabled { background-color: #BDC3C7; }
"""
