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
    QSizePolicy, QTextEdit,
)
from PySide6.QtCore import Qt, Signal, QThread, QSize
from PySide6.QtGui import QFont, QColor, QIcon, QDragEnterEvent, QDropEvent

from ...base_tool_widget import BaseToolWidget
from . import engine


class AnalysisWorker(QThread):
    """后台分析线程，避免 UI 卡死"""

    progress = Signal(str)       # 进度消息
    finished = Signal(dict)      # 分析结果
    error = Signal(str)          # 错误消息

    def __init__(self, log_files: list[str]):
        super().__init__()
        self._log_files = log_files

    def run(self):
        try:
            self.progress.emit(f"正在分析 {len(self._log_files)} 个文件...")
            results = engine.run_analysis(self._log_files)

            # 提取分析日志
            analysis_log = results.pop("__analysis_log__", [])

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
        title = QLabel("🔍 指纹解锁速度分析")
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

        # 操作按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._btn_add = QPushButton("📁 添加文件")
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
            QPushButton:hover {
                background-color: #2980B9;
            }
            QPushButton:pressed {
                background-color: #2472A4;
            }
        """)
        self._btn_add.clicked.connect(self._on_add_files)
        btn_row.addWidget(self._btn_add)

        self._btn_clear = QPushButton("🗑 清空")
        self._btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #95A5A6;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #7F8C8D;
            }
        """)
        self._btn_clear.clicked.connect(self._on_clear_files)
        btn_row.addWidget(self._btn_clear)

        btn_row.addStretch()

        self._lbl_file_count = QLabel("已选择 0 个文件")
        self._lbl_file_count.setStyleSheet("font-size: 13px; color: #7F8C8D;")
        btn_row.addWidget(self._lbl_file_count)

        file_layout.addLayout(btn_row)

        # 文件列表（支持拖拽）
        self._file_list = DropListWidget()
        self._file_list.files_dropped.connect(self._on_files_dropped)
        self._file_list.setMinimumHeight(100)
        file_layout.addWidget(self._file_list)

        # 提示标签
        hint = QLabel("💡 支持拖拽 .log / .txt / .zip 文件到上方区域")
        hint.setStyleSheet("font-size: 12px; color: #BDC3C7;")
        hint.setAlignment(Qt.AlignCenter)
        file_layout.addWidget(hint)

        layout.addWidget(file_group)

        # ---- 操作按钮行 ----
        action_row = QHBoxLayout()
        action_row.setSpacing(15)

        self._btn_analyze = QPushButton("▶ 开始分析")
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
            QPushButton:hover {
                background-color: #219A52;
            }
            QPushButton:disabled {
                background-color: #BDC3C7;
            }
        """)
        self._btn_analyze.clicked.connect(self._on_analyze)
        action_row.addWidget(self._btn_analyze)

        self._btn_export = QPushButton("📊 导出 Excel")
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
            QPushButton:hover {
                background-color: #7D3C98;
            }
            QPushButton:disabled {
                background-color: #BDC3C7;
            }
        """)
        self._btn_export.clicked.connect(self._on_export)
        self._btn_export.setEnabled(False)
        action_row.addWidget(self._btn_export)

        self._btn_open_dir = QPushButton("📂 打开输出目录")
        self._btn_open_dir.setStyleSheet("""
            QPushButton {
                background-color: #E67E22;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #D35400;
            }
        """)
        self._btn_open_dir.clicked.connect(self._on_open_output_dir)
        action_row.addWidget(self._btn_open_dir)

        self._btn_open_filtered = QPushButton("📋 查看过滤日志")
        self._btn_open_filtered.setStyleSheet("""
            QPushButton {
                background-color: #16A085;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #138D75;
            }
        """)
        self._btn_open_filtered.clicked.connect(self._on_open_filtered_dir)
        action_row.addWidget(self._btn_open_filtered)

        action_row.addStretch()
        layout.addLayout(action_row)

        # ---- 进度条 ----
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # 忙碌模式
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

        # ---- 结果表格 ----
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
            QTableWidget::item {
                padding: 6px 10px;
            }
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

        # 分析日志输出区
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

        # 状态变量
        self._log_files = []
        self._results = {}

    def _on_add_files(self):
        """添加文件按钮"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择日志文件", "",
            "日志文件 (*.log *.txt *.zip);;所有文件 (*.*)"
        )
        if files:
            self._on_files_dropped(files)

    def _on_files_dropped(self, files: list[str]):
        """拖拽或选择文件"""
        for f in files:
            if f not in self._log_files:
                self._log_files.append(f)
                item = QListWidgetItem(f)
                self._file_list.addItem(item)
        self._update_file_count()

    def _on_clear_files(self):
        """清空文件列表"""
        self._log_files.clear()
        self._file_list.clear()
        self._update_file_count()
        self._results = {}
        self._btn_export.setEnabled(False)
        self._table.setRowCount(0)
        self._table.setColumnCount(0)
        self._log_output.clear()

    def _update_file_count(self):
        """更新文件计数"""
        self._lbl_file_count.setText(f"已选择 {len(self._log_files)} 个文件")
        self._btn_analyze.setEnabled(len(self._log_files) > 0)

    def _on_analyze(self):
        """开始分析"""
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
        self._lbl_progress.setText("分析完成 ✓")

        # 清除旧日志
        self._log_output.clear()

        total = sum(len(v) for v in results.values())
        if total == 0:
            self._log_output.append("⚠ 未检测到有效的指纹解锁流程")
            self._log_output.append("可能原因:")
            self._log_output.append("  1. 日志文件不包含指纹相关日志 (检查是否包含 gf_hal / EVENT_FINGER_DOWN 等关键字)")
            self._log_output.append("  2. 日志中缺少 'Auth success' 或 'onAuthenticated' 事件")
            self._log_output.append("  3. 过滤后的日志文件在 filtered_logs/ 目录下，可手动检查")
            QMessageBox.information(self, "提示", "未检测到有效的指纹解锁流程\n\n过滤后的日志文件保存在 filtered_logs/ 目录下\n可打开查看是否包含指纹相关关键字")
            return

        # 填充结果表格
        self._populate_table(results)
        self._btn_export.setEnabled(True)

        # 显示分析摘要
        self._log_output.append(f"✅ 分析完成，共 {total} 次成功解锁")
        for name, unlocks in results.items():
            types = {}
            for u in unlocks:
                t = u.get("_unlock_type", "未知")
                types[t] = types.get(t, 0) + 1
            type_str = ", ".join(f"{k}={v}" for k, v in types.items())
            self._log_output.append(f"  [{name}]: {len(unlocks)} 次解锁 ({type_str})")
        self._log_output.append(f"📂 过滤日志: {os.path.abspath(engine.FILTERED_DIR)}/")
        self._log_output.append(f"📂 输出目录: {os.path.abspath(engine.OUTPUT_DIR)}/")

    def _on_analysis_error(self, err: str):
        self._progress.hide()
        self._btn_analyze.setEnabled(True)
        self._lbl_progress.setText("分析失败 ✗")
        self._log_output.clear()
        self._log_output.append(f"❌ 分析错误:\n{err}")
        QMessageBox.critical(self, "分析错误", f"分析过程中发生错误:\n{err}")

    def _populate_table(self, results: dict):
        """将分析结果填入表格"""
        # 构建扁平数据
        rows = []
        for log_name, unlocks in results.items():
            for u in unlocks:
                fd = engine.format_ts(u.get("手指按压"))
                utype = u.get("_unlock_type", "未知")
                base = engine.calc_delta_ms(u.get("手指按压"), u.get("指纹匹配成功"))
                total = engine.calc_delta_ms(u.get("手指按压"), u.get("开始显示应用画面"))
                hal = u.get("HAL按压到解锁(ms)", "-")
                kpi = u.get("HAL算法时间(ms)", "-")
                rows.append([log_name, utype, fd, base, total, hal, kpi])

        headers = ["日志文件", "解锁类型", "按压时间", "底层(ms)", "总耗时(ms)", "HAL(ms)", "KPI(ms)"]
        self._table.setColumnCount(len(headers))
        self._table.setRowCount(len(rows))
        self._table.setHorizontalHeaderLabels(headers)

        for r, row_data in enumerate(rows):
            for c, val in enumerate(row_data):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignCenter)
                self._table.setItem(r, c, item)

        self._table.resizeColumnsToContents()

    def _on_export(self):
        """导出 Excel"""
        if not self._results:
            QMessageBox.warning(self, "提示", "没有可导出的结果")
            return

        # 按文件分组的结果
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

    def _on_open_output_dir(self):
        """打开输出目录"""
        output_dir = os.path.join(os.getcwd(), engine.OUTPUT_DIR)
        os.makedirs(output_dir, exist_ok=True)
        os.startfile(output_dir)

    def _on_open_filtered_dir(self):
        """打开过滤日志目录"""
        filtered_dir = os.path.join(os.getcwd(), engine.FILTERED_DIR)
        os.makedirs(filtered_dir, exist_ok=True)
        os.startfile(filtered_dir)