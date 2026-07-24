"""
指纹解锁速度分析 - GUI 工具界面
"""

import os
import threading
import glob
import traceback

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QListWidget, QListWidgetItem, QTableWidget,
    QTableWidgetItem, QProgressBar, QMessageBox, QFrame,
    QSplitter, QAbstractItemView, QHeaderView, QGroupBox,
    QSizePolicy, QTextEdit, QComboBox, QDialog, QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal, QThread, QSize
from PySide6.QtGui import (
    QFont, QColor, QBrush, QIcon,
    QDragEnterEvent, QDropEvent,
)

from ...base_tool_widget import BaseToolWidget
from . import engine


class AnalysisWorker(QThread):
    """后台分析线程，避免 UI 卡死"""

    progress = Signal(str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, log_files: list[str]):
        super().__init__()
        self._log_files = log_files

    def run(self):
        try:
            self.progress.emit(f"正在分析 {len(self._log_files)} 个文件...")
            results = engine.run_analysis(self._log_files)
            results.pop("__analysis_log__", [])
            total = sum(len(v) for v in results.values())
            self.progress.emit(f"分析完成，共 {total} 次成功解锁")
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(traceback.format_exc())


class DropListWidget(QListWidget):
    """支持拖拽的文件列表"""

    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setStyleSheet("""
            QListWidget {
                border: 2px dashed #BDC3C7;
                border-radius: 8px;
                background-color: #FAFAFA;
                padding: 10px;
                font-size: 13px;
            }
            QListWidget:focus {
                border-color: #3498DB;
            }
            QListWidget::item {
                padding: 6px 10px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #3498DB;
                color: white;
            }
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
            if os.path.isfile(path) and path.lower().endswith(('.log', '.txt', '.zip')):
                files.append(path)
        if files:
            self.files_dropped.emit(files)


class FingerprintAnalysisWidget(BaseToolWidget):
    """指纹解锁速度分析工具"""

    def tool_name(self) -> str:
        return "指纹解锁速度分析"

    def tool_tip(self) -> str:
        return "分析 Android 指纹解锁日志，统计解锁时间并生成 Excel 报告"

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # ---- 标题 ----
        title = QLabel("指纹解锁速度分析")
        title.setStyleSheet("""
            font-size: 22px;
            font-weight: bold;
            color: #2C3E50;
            margin-bottom: 5px;
        """)
        layout.addWidget(title)

        desc = QLabel("选择 Android 日志文件（.log/.txt/.zip），分析指纹解锁各阶段耗时")
        desc.setStyleSheet("font-size: 13px; color: #7F8C8D;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # ---- 文件选择区 ----
        file_group = QGroupBox("文件选择")
        file_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #2C3E50;
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                margin-top: 12px;
                padding: 15px 10px 10px 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                background-color: #F5F6FA;
            }
        """)

        file_layout = QVBoxLayout(file_group)
        file_layout.setSpacing(10)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._btn_add = QPushButton("添加文件")
        self._btn_add.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2980B9; }
            QPushButton:pressed { background-color: #2472A4; }
        """)
        self._btn_add.clicked.connect(self._on_add_files)
        btn_row.addWidget(self._btn_add)

        self._btn_clear = QPushButton("清空")
        self._btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #95A5A6;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #7F8C8D; }
        """)
        self._btn_clear.clicked.connect(self._on_clear_files)
        btn_row.addWidget(self._btn_clear)

        btn_row.addStretch()

        self._lbl_file_count = QLabel("已选择 0 个文件")
        self._lbl_file_count.setStyleSheet("font-size: 13px; color: #7F8C8D;")
        btn_row.addWidget(self._lbl_file_count)

        file_layout.addLayout(btn_row)

        self._file_list = DropListWidget()
        self._file_list.files_dropped.connect(self._on_files_dropped)
        self._file_list.setMinimumHeight(100)
        file_layout.addWidget(self._file_list)

        hint = QLabel("支持拖拽 .log / .txt / .zip 文件到上方区域")
        hint.setStyleSheet("font-size: 12px; color: #BDC3C7;")
        hint.setAlignment(Qt.AlignCenter)
        file_layout.addWidget(hint)

        layout.addWidget(file_group)

        # ---- 操作按钮行 ----
        action_row = QHBoxLayout()
        action_row.setSpacing(15)

        self._btn_analyze = QPushButton("开始分析")
        self._btn_analyze.setStyleSheet("""
            QPushButton {
                background-color: #27AE60;
                color: white;
                border: none;
                padding: 10px 30px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #219A52; }
            QPushButton:disabled { background-color: #BDC3C7; }
        """)
        self._btn_analyze.clicked.connect(self._on_analyze)
        action_row.addWidget(self._btn_analyze)

        self._btn_export = QPushButton("导出 Excel")
        self._btn_export.setStyleSheet("""
            QPushButton {
                background-color: #8E44AD;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #7D3C98; }
            QPushButton:disabled { background-color: #BDC3C7; }
        """)
        self._btn_export.clicked.connect(self._on_export)
        self._btn_export.setEnabled(False)
        action_row.addWidget(self._btn_export)

        self._btn_preview = QPushButton("放大预览")
        self._btn_preview.setStyleSheet("""
            QPushButton {
                background-color: #2980B9;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2472A4; }
            QPushButton:disabled { background-color: #BDC3C7; }
        """)
        self._btn_preview.clicked.connect(self._on_preview)
        self._btn_preview.setEnabled(False)
        action_row.addWidget(self._btn_preview)

        self._btn_open_dir = QPushButton("打开输出目录")
        self._btn_open_dir.setStyleSheet("""
            QPushButton {
                background-color: #E67E22;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #D35400; }
        """)
        self._btn_open_dir.clicked.connect(self._on_open_output_dir)
        action_row.addWidget(self._btn_open_dir)

        self._btn_open_filtered = QPushButton("查看过滤日志")
        self._btn_open_filtered.setStyleSheet("""
            QPushButton {
                background-color: #16A085;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #138D75; }
        """)
        self._btn_open_filtered.clicked.connect(self._on_open_filtered_dir)
        action_row.addWidget(self._btn_open_filtered)

        action_row.addStretch()
        layout.addLayout(action_row)

        # ---- 进度条 ----
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(6)
        self._progress.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #ECF0F1;
                border-radius: 3px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #3498DB;
                border-radius: 3px;
            }
        """)
        self._progress.hide()
        layout.addWidget(self._progress)

        self._lbl_progress = QLabel("")
        self._lbl_progress.setStyleSheet("font-size: 12px; color: #7F8C8D;")
        self._lbl_progress.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._lbl_progress)

        # ---- 结果区 ----
        result_group = QGroupBox("分析结果")
        result_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #2C3E50;
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                margin-top: 12px;
                padding: 15px 10px 10px 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                background-color: #F5F6FA;
            }
        """)

        result_layout = QVBoxLayout(result_group)

        # 日志选择器（多日志时切换）
        selector_row = QHBoxLayout()
        selector_label = QLabel("选择日志:")
        selector_label.setStyleSheet("font-size: 13px; color: #2C3E50; font-weight: bold;")
        selector_row.addWidget(selector_label)
        self._log_selector = QComboBox()
        self._log_selector.setMinimumWidth(300)
        self._log_selector.setStyleSheet("""
            QComboBox {
                font-size: 13px;
                padding: 4px 10px;
                border: 1px solid #BDC3C7;
                border-radius: 4px;
                background-color: white;
            }
            QComboBox:hover { border-color: #3498DB; }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid #BDC3C7;
            }
        """)
        self._log_selector.currentIndexChanged.connect(self._on_log_selected)
        selector_row.addWidget(self._log_selector)
        selector_row.addStretch()

        self._lbl_summary = QLabel("")
        self._lbl_summary.setStyleSheet("font-size: 12px; color: #7F8C8D;")
        selector_row.addWidget(self._lbl_summary)
        result_layout.addLayout(selector_row)

        self._table = QTableWidget()
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                background-color: white;
                gridline-color: #ECF0F1;
                font-size: 13px;
            }
            QTableWidget::item { padding: 6px 10px; }
            QTableWidget::item:selected {
                background-color: #3498DB;
                color: white;
            }
            QHeaderView::section {
                background-color: #2C3E50;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 8px;
                border: 1px solid #34495E;
            }
        """)
        result_layout.addWidget(self._table, 3)

        # 分析日志
        log_label = QLabel("分析日志")
        log_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #7F8C8D; margin-top: 5px;")
        result_layout.addWidget(log_label)

        self._log_output = QTextEdit()
        self._log_output.setReadOnly(True)
        self._log_output.setMaximumHeight(150)
        self._log_output.setStyleSheet("""
            QTextEdit {
                background-color: #2C3E50;
                color: #ECF0F1;
                border: 1px solid #34495E;
                border-radius: 4px;
                font-family: Consolas, monospace;
                font-size: 12px;
                padding: 8px;
            }
        """)
        result_layout.addWidget(self._log_output)

        layout.addWidget(result_group, 1)

        self._main_layout.addLayout(layout)

        self._log_files = []
        self._results = {}

    def _on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择日志文件", "",
            "日志文件 (*.log *.txt *.zip);;所有文件 (*.*)"
        )
        if files:
            self._on_files_dropped(files)

    def _on_files_dropped(self, files: list[str]):
        for f in files:
            if f not in self._log_files:
                self._log_files.append(f)
                item = QListWidgetItem(f)
                self._file_list.addItem(item)
        self._update_file_count()

    def _on_clear_files(self):
        self._log_files.clear()
        self._file_list.clear()
        self._update_file_count()
        self._results = {}
        self._btn_export.setEnabled(False)
        self._btn_preview.setEnabled(False)
        self._table.setRowCount(0)
        self._table.setColumnCount(0)
        self._log_output.clear()
        self._log_selector.clear()
        self._lbl_summary.clear()

    def _update_file_count(self):
        self._lbl_file_count.setText(f"已选择 {len(self._log_files)} 个文件")
        self._btn_analyze.setEnabled(len(self._log_files) > 0)

    def _on_analyze(self):
        if not self._log_files:
            QMessageBox.warning(self, "提示", "请先添加日志文件")
            return

        self._btn_analyze.setEnabled(False)
        self._progress.show()
        self._lbl_progress.setText("正在分析中...")
        self._table.setRowCount(0)
        self._table.setColumnCount(0)
        self._btn_export.setEnabled(False)
        self._log_output.clear()
        self._log_selector.clear()
        self._lbl_summary.clear()

        self._worker = AnalysisWorker(self._log_files)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_analysis_finished)
        self._worker.error.connect(self._on_analysis_error)
        self._worker.start()

    def _on_progress(self, msg: str):
        self._lbl_progress.setText(msg)

    def _on_analysis_finished(self, results: dict):
        self._results = results
        self._progress.hide()
        self._btn_analyze.setEnabled(True)
        self._lbl_progress.setText("分析完成")

        self._log_output.clear()
        total = sum(len(v) for v in results.values())

        if total == 0:
            self._log_output.append("未检测到有效的指纹解锁流程")
            self._log_output.append("可能原因:")
            self._log_output.append("  1. 日志文件不包含指纹相关日志")
            self._log_output.append("  2. 日志中缺少 'Auth success' 或 'onAuthenticated' 事件")
            self._log_output.append("  3. 过滤后的日志文件在 filtered_logs/ 目录下，可手动检查")
            QMessageBox.information(self, "提示", "未检测到有效的指纹解锁流程\n过滤后的日志文件保存在 filtered_logs/ 目录下")
            return

        # 填充日志选择器
        self._log_selector.blockSignals(True)
        self._log_selector.clear()
        for name in results.keys():
            self._log_selector.addItem(name, userData=results[name])
        self._log_selector.blockSignals(False)
        self._log_selector.setCurrentIndex(0)
        self._on_log_selected(0)

        self._btn_export.setEnabled(True)
        self._btn_preview.setEnabled(True)

        # 摘要
        self._log_output.append(f"分析完成，共 {total} 次成功解锁")
        for name, unlocks in results.items():
            types = {}
            for u in unlocks:
                t = u.get("_unlock_type", "未知")
                types[t] = types.get(t, 0) + 1
            type_str = ", ".join(f"{k}={v}" for k, v in types.items())
            self._log_output.append(f"  [{name}]: {len(unlocks)} 次解锁 ({type_str})")
        self._log_output.append(f"过滤日志: {os.path.abspath(engine.FILTERED_DIR)}/")
        self._log_output.append(f"输出目录: {os.path.abspath(engine.OUTPUT_DIR)}/")

    def _on_log_selected(self, index: int):
        if index < 0:
            return
        unlocks = self._log_selector.currentData() or []
        self._populate_table(unlocks)
        self._update_summary(unlocks)

    def _update_summary(self, unlocks: list):
        types = {}
        for u in unlocks:
            t = u.get("_unlock_type", "未知")
            types[t] = types.get(t, 0) + 1
        parts = [f"{ut}: {types.get(ut, 0)}次" for ut in ["息屏解锁", "AOD解锁", "亮屏解锁"] if ut in types]
        self._lbl_summary.setText(" | ".join(parts))

    def _populate_table(self, unlocks: list[dict]):
        """完整详情表格，与 Excel 输出一致"""
        self._do_populate_table(self._table, unlocks)

    def _on_analysis_error(self, err: str):
        self._progress.hide()
        self._btn_analyze.setEnabled(True)
        self._lbl_progress.setText("分析失败")
        self._log_output.clear()
        self._log_output.append(f"分析错误:\n{err}")
        QMessageBox.critical(self, "分析错误", f"分析过程中发生错误:\n{err}")

    def _on_export(self):
        if not self._results:
            QMessageBox.warning(self, "提示", "没有可导出的结果")
            return

        from collections import defaultdict
        grouped = defaultdict(list)
        for log_name, unlocks in self._results.items():
            grouped[log_name] = unlocks

        default_name = "fingerprint_unlock_analysis.xlsx"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "保存 Excel 报告", default_name,
            "Excel 文件 (*.xlsx);;所有文件 (*.*)"
        )
        if not filepath:
            return

        try:
            engine.write_excel(dict(grouped), filepath)
            QMessageBox.information(self, "导出成功", f"Excel 报告已保存:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出 Excel 时出错:\n{e}")

    def _on_preview(self):
        """打开放大预览窗口"""
        if not self._results:
            QMessageBox.warning(self, "提示", "没有可预览的结果")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("指纹解锁分析 - 放大预览")
        dlg.setWindowFlags(
            dlg.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint
        )
        dlg.resize(1280, 800)
        dlg.setMinimumSize(800, 500)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 日志选择器
        top_row = QHBoxLayout()
        top_label = QLabel("选择日志:")
        top_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        top_row.addWidget(top_label)
        selector = QComboBox()
        selector.setMinimumWidth(300)
        for name in self._results.keys():
            selector.addItem(name, userData=self._results[name])
        selector.setCurrentIndex(self._log_selector.currentIndex())
        top_row.addWidget(selector)
        top_row.addStretch()
        layout.addLayout(top_row)

        # 大表格
        table = QTableWidget()
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                background-color: white;
                gridline-color: #ECF0F1;
                font-size: 13px;
            }
            QTableWidget::item { padding: 6px 10px; }
            QTableWidget::item:selected {
                background-color: #3498DB;
                color: white;
            }
            QHeaderView::section {
                background-color: #2C3E50;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 8px;
                border: 1px solid #34495E;
            }
        """)
        layout.addWidget(table, 1)

        # 底部按钮
        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        # 填充表格的函数
        def _fill_table(unlocks):
            self._do_populate_table(table, unlocks)

        _fill_table(selector.currentData() or [])
        selector.currentIndexChanged.connect(
            lambda idx: _fill_table(selector.currentData() or [])
        )

        dlg.exec()

    def _do_populate_table(self, table: QTableWidget, unlocks: list[dict]):
        """将数据填充到指定的表格（复用逻辑）"""
        STEP_LABELS = engine.STEPS
        headers = ["解锁次数", "解锁类型"]
        for i, (kw, label, mode) in enumerate(STEP_LABELS):
            if mode == "timestamp":
                headers.append(f"{label}\n(时间戳)")
                if i > 0:
                    headers.append("距上一步(ms)")
            elif mode in ("extract_ms", "extract_ms_capture"):
                headers.append(label)
        headers.append("底层时间(ms)\nFINGER_DOWN->Auth")
        headers.append("总解锁时间(ms)\nFINGER_DOWN->画面")

        YELLOW = QColor("#FFF2CC")
        LIGHT_BLUE = QColor("#DDEBF7")
        GREEN = QColor("#E2EFDA")
        BLUE = QColor("#0070C0")
        RED = QColor("#FF0000")

        type_rows = {"息屏解锁": [], "AOD解锁": [], "亮屏解锁": []}
        for idx, u in enumerate(unlocks):
            ut = u.get("_unlock_type", "亮屏解锁")
            if ut in type_rows:
                type_rows[ut].append(idx)

        avg_count = sum(1 for v in type_rows.values() if v)
        total_rows = len(unlocks) + 1 + avg_count

        table.setColumnCount(len(headers))
        table.setRowCount(total_rows)
        table.setHorizontalHeaderLabels(headers)

        def _cell(row, col, text, bg=None, fg=None, bold=False):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            if bg:
                item.setBackground(QBrush(bg))
            if fg:
                item.setForeground(QBrush(fg))
            if bold:
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            table.setItem(row, col, item)

        for idx, unlock in enumerate(unlocks):
            row = idx
            finger_down_ts = unlock.get("手指按压")
            auth_success_ts = unlock.get("指纹匹配成功")
            app_vis_ts = unlock.get("开始显示应用画面")
            unlock_type = unlock.get("_unlock_type", "亮屏解锁")

            row_bg = None
            if unlock_type == "亮屏解锁":
                row_bg = YELLOW
            elif unlock_type == "AOD解锁":
                row_bg = LIGHT_BLUE

            col = 0
            _cell(row, col, f"第{idx + 1}次", bg=row_bg)
            col += 1
            _cell(row, col, unlock_type, bg=row_bg)
            col += 1

            prev_ts = None
            for i, (kw, label, mode) in enumerate(STEP_LABELS):
                val = unlock.get(label)
                if mode == "timestamp":
                    _cell(row, col, engine.format_ts(val), bg=row_bg)
                    col += 1
                    if i > 0:
                        delta = engine.calc_delta_ms(prev_ts, val) if isinstance(val, engine.datetime) else "-"
                        _cell(row, col, delta, bg=row_bg)
                        col += 1
                    if isinstance(val, engine.datetime):
                        prev_ts = val
                elif mode in ("extract_ms", "extract_ms_capture"):
                    _cell(row, col, val if val else "-", bg=row_bg)
                    col += 1

            base_time = engine.calc_delta_ms(finger_down_ts, auth_success_ts)
            _cell(row, col, base_time, bg=row_bg, fg=BLUE if base_time != "-" else None)
            col += 1

            total_time = engine.calc_delta_ms(finger_down_ts, app_vis_ts)
            _cell(row, col, total_time if total_time != "-" else "(无画面切换)", bg=row_bg, fg=RED if total_time != "-" else None)

        current_row = len(unlocks) + 1
        for utype in ["息屏解锁", "AOD解锁", "亮屏解锁"]:
            rows_of_type = type_rows.get(utype, [])
            if not rows_of_type:
                continue
            _cell(current_row, 0, f"{utype} 平均值 ({len(rows_of_type)}次)", bg=GREEN, bold=True)
            _cell(current_row, 1, "", bg=GREEN)
            for col_idx in range(2, len(headers)):
                vals = []
                for r in rows_of_type:
                    it = table.item(r, col_idx)
                    if it and it.text():
                        fv = engine._safe_float(it.text())
                        if fv is not None:
                            vals.append(fv)
                if vals:
                    _cell(current_row, col_idx, f"{sum(vals) / len(vals):.1f}", bg=GREEN, bold=True)
                else:
                    _cell(current_row, col_idx, "-", bg=GREEN, bold=True)
            current_row += 1

        table.resizeColumnsToContents()

    def _on_open_output_dir(self):
        output_dir = os.path.join(os.getcwd(), engine.OUTPUT_DIR)
        os.makedirs(output_dir, exist_ok=True)
        os.startfile(output_dir)

    def _on_open_filtered_dir(self):
        filtered_dir = os.path.join(os.getcwd(), engine.FILTERED_DIR)
        os.makedirs(filtered_dir, exist_ok=True)
        os.startfile(filtered_dir)