"""
日志实时抓取工具 - PySide6 版本
支持 logcat / kmsg / qsee_log 三种日志类型
"""

import os
import subprocess
import threading
import time
import queue

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QTextEdit, QComboBox, QFileDialog, QMessageBox,
    QCheckBox, QLineEdit, QProgressBar, QTabWidget, QSplitter,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer

from ...base_tool_widget import BaseToolWidget

HISTORY_FILE = "log_keyword_history.txt"
DEFAULT_DIR = "D:/Joyboy"

LOG_TYPES = {
    "logcat": {"label": "Logcat", "cmd": ["adb", "shell", "logcat"]},
    "kmsg": {"label": "Kmsg", "cmd": ["adb", "shell", "cat", "/proc/kmsg"]},
    "qsee_log": {"label": "QSee Log", "cmd": ["adb", "shell", "cat", "/proc/tzdbg/qsee_log"]},
}


class LogCaptureWorker(QThread):
    """日志抓取后台线程"""
    output = Signal(str)
    finished = Signal()

    def __init__(self, log_type: str, keywords: list[str], case_sensitive: bool, save_path: str):
        super().__init__()
        self._log_type = log_type
        self._keywords = keywords
        self._case = case_sensitive
        self._save_path = save_path
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        cmd = LOG_TYPES[self._log_type]["cmd"]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True,
                                    encoding="utf-8", errors="replace")
            fout = open(self._save_path, "a", encoding="utf-8", errors="replace")
            buffer = []
            last_flush = time.time()

            while self._running:
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        break
                    time.sleep(0.1)
                    continue

                if self._match(line):
                    buffer.append(line)
                    self.output.emit(line.rstrip())

                    if len(buffer) >= 100 or (time.time() - last_flush) > 0.5:
                        fout.writelines(buffer)
                        buffer.clear()
                        last_flush = time.time()

            if buffer:
                fout.writelines(buffer)
            fout.close()
            proc.terminate()
        except Exception as e:
            self.output.emit(f"ERROR: {e}")
        finally:
            self.finished.emit()

    def _match(self, line: str) -> bool:
        if not self._keywords or self._keywords == [""]:
            return True
        check = line if self._case else line.lower()
        return any(
            (kw if self._case else kw.lower()) in check
            for kw in self._keywords
        )


class LogCaptureWidget(BaseToolWidget):
    def tool_name(self) -> str:
        return "日志抓取"

    def tool_tip(self) -> str:
        return "实时抓取 Android 设备日志（logcat/kmsg/qsee_log）并过滤关键字"

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("日志实时抓取")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #2C3E50;")
        layout.addWidget(title)

        self._workers = {}
        self._capture_outputs = {}

        # 日志类型选择区
        self._tabs = {}
        config_group = QGroupBox("日志配置")
        config_layout = QVBoxLayout(config_group)

        for ltype, info in LOG_TYPES.items():
            row = QHBoxLayout()
            row.setSpacing(8)

            cb = QCheckBox(info["label"])
            cb.setStyleSheet("font-size: 13px; font-weight: bold;")
            row.addWidget(cb)

            kw_label = QLabel("关键词(逗号分隔):")
            kw_label.setStyleSheet("font-size: 12px;")
            row.addWidget(kw_label)
            kw_input = QLineEdit()
            kw_input.setPlaceholderText("例如: error,trace")
            kw_input.setMinimumWidth(150)
            row.addWidget(kw_input, 1)

            case_cb = QCheckBox("区分大小写")
            case_cb.setStyleSheet("font-size: 12px;")
            row.addWidget(case_cb)

            path_input = QLineEdit()
            path_input.setText(f"{DEFAULT_DIR}/{ltype}.txt")
            path_input.setMinimumWidth(150)
            row.addWidget(path_input, 1)

            btn_browse = QPushButton("...")
            btn_browse.setFixedWidth(30)
            btn_browse.clicked.connect(lambda checked, p=path_input: self._browse(p))
            row.addWidget(btn_browse)

            config_layout.addLayout(row)
            self._tabs[ltype] = {
                "enabled": cb, "keywords": kw_input, "case": case_cb, "path": path_input
            }

        layout.addWidget(config_group)

        # 操作按钮
        btn_row = QHBoxLayout()
        self._btn_start = QPushButton("开始抓取")
        self._btn_start.setStyleSheet("""
            QPushButton { background-color: #27AE60; color: white; padding: 10px 30px;
                border-radius: 6px; font-size: 14px; font-weight: bold; border: none; }
            QPushButton:hover { background-color: #219A52; }
        """)
        self._btn_start.clicked.connect(self._start_capture)
        btn_row.addWidget(self._btn_start)

        self._btn_stop = QPushButton("停止全部")
        self._btn_stop.setStyleSheet("""
            QPushButton { background-color: #E74C3C; color: white; padding: 10px 30px;
                border-radius: 6px; font-size: 14px; font-weight: bold; border: none; }
            QPushButton:hover { background-color: #C0392B; }
        """)
        self._btn_stop.clicked.connect(self._stop_all)
        btn_row.addWidget(self._btn_stop)

        self._status_label = QLabel("就绪")
        self._status_label.setStyleSheet("font-size: 13px; color: #7F8C8D;")
        btn_row.addWidget(self._status_label)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 输出区（分 tab 显示）
        self._output_tabs = QTabWidget()
        self._output_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #CCC; background: #1E1E1E; }
            QTabBar::tab { padding: 6px 15px; font-size: 13px; }
            QTabBar::tab:selected { background: #3498DB; color: white; }
        """)
        layout.addWidget(self._output_tabs, 1)

        self._main_layout.addLayout(layout)

    def _browse(self, path_input):
        path, _ = QFileDialog.getSaveFileName(self, "保存日志文件", "", "日志文件 (*.txt *.log);;所有文件 (*.*)")
        if path:
            path_input.setText(path)

    def _save_keywords(self, keywords_str):
        if not keywords_str:
            return
        try:
            history = []
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    history = [line.strip() for line in f.readlines() if line.strip()]
            if keywords_str in history:
                history.remove(keywords_str)
            history.insert(0, keywords_str)
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                for item in history[:20]:
                    f.write(f"{item}\n")
        except Exception:
            pass

    def _start_capture(self):
        self._stop_all()

        os.makedirs(DEFAULT_DIR, exist_ok=True)
        started = 0

        for ltype, info in LOG_TYPES.items():
            ctrls = self._tabs[ltype]
            if not ctrls["enabled"].isChecked():
                continue

            keywords_str = ctrls["keywords"].text().strip()
            save_path = ctrls["path"].text().strip()
            if not save_path:
                QMessageBox.warning(self, "警告", f"请填写 {info['label']} 的保存路径")
                return

            self._save_keywords(keywords_str)
            keywords = [k.strip() for k in keywords_str.split(",")] if keywords_str else []
            case = ctrls["case"].isChecked()

            # 创建输出 tab
            output = QTextEdit()
            output.setReadOnly(True)
            output.setStyleSheet("""
                QTextEdit { background-color: #1E1E1E; color: #D4D4D4; font-family: Consolas;
                    font-size: 13px; border: none; padding: 8px; }
            """)
            idx = self._output_tabs.addTab(output, info["label"])
            self._capture_outputs[ltype] = output

            worker = LogCaptureWorker(ltype, keywords, case, save_path)
            worker.output.connect(lambda text, lt=ltype: self._on_output(lt, text))
            worker.finished.connect(lambda lt=ltype: self._on_finished(lt))
            worker.start()
            self._workers[ltype] = worker
            started += 1

        if started == 0:
            QMessageBox.warning(self, "警告", "请至少勾选一个日志类型")
            return
        self._status_label.setText(f"正在抓取 {started} 个日志...")
        self._status_label.setStyleSheet("font-size: 13px; color: green; font-weight: bold;")

    def _on_output(self, ltype, text):
        if ltype in self._capture_outputs:
            self._capture_outputs[ltype].append(text)

    def _on_finished(self, ltype):
        if ltype in self._workers:
            del self._workers[ltype]
        if not self._workers:
            self._status_label.setText("已停止")
            self._status_label.setStyleSheet("font-size: 13px; color: #7F8C8D;")

    def _stop_all(self):
        for ltype, worker in list(self._workers.items()):
            worker.stop()
            worker.wait(1000)
        self._workers.clear()
        self._capture_outputs.clear()
        while self._output_tabs.count() > 0:
            self._output_tabs.removeTab(0)
        self._status_label.setText("已停止")
        self._status_label.setStyleSheet("font-size: 13px; color: #7F8C8D;")

    def on_deactivate(self):
        self._stop_all()