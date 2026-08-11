"""
ADB 单刷工具 - PySide6 版本
"""

import os
import json
import time
import subprocess
import threading
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QTextEdit, QComboBox, QFileDialog, QMessageBox,
    QLineEdit, QProgressBar,
)
from PySide6.QtCore import Qt, Signal, QThread

from ...base_tool_widget import BaseToolWidget


HISTORY_FILE = "adb_file_history.json"
TARGET_HISTORY_FILE = "adb_target_history.json"


class FlashWorker(QThread):
    """ADB 刷写后台线程"""
    output = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, file_path: str, target_path: str):
        super().__init__()
        self._file = file_path
        self._target = target_path

    def run(self):
        try:
            for cmd in [
                "adb wait-for-device",
                "adb root",
                "adb disable-verity",
            ]:
                self.output.emit(f">>> {cmd}")
                p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                self.output.emit(p.stdout.strip())
                if p.returncode != 0:
                    self.output.emit(p.stderr.strip())
                    if cmd == "adb disable-verity":
                        self.output.emit("disable-verity failed, rebooting...")
                        subprocess.run("adb reboot", shell=True, timeout=10)
                        time.sleep(20)
                        subprocess.run("adb wait-for-device", shell=True, timeout=60)
                        subprocess.run("adb root", shell=True, timeout=30)
                        continue
                    raise RuntimeError(f"Command failed: {cmd}")

            self.output.emit(">>> adb remount")
            p = subprocess.run("adb remount", shell=True, capture_output=True, text=True, timeout=30)
            self.output.emit(p.stdout.strip())
            if p.returncode != 0:
                raise RuntimeError(f"remount failed: {p.stderr.strip()}")

            push_cmd = f'adb push "{self._file}" "{self._target}"'
            self.output.emit(f">>> {push_cmd}")
            p = subprocess.run(push_cmd, shell=True, capture_output=True, text=True, timeout=120)
            self.output.emit(p.stdout.strip())
            if p.returncode != 0:
                raise RuntimeError(f"push failed: {p.stderr.strip()}")

            self.output.emit("SUCCESS: File pushed successfully!")
            self.finished.emit(True, "File pushed successfully!")
        except Exception as e:
            self.output.emit(f"ERROR: {e}")
            self.finished.emit(False, str(e))


class ADBFlashWidget(BaseToolWidget):
    """ADB 单刷工具"""

    def tool_name(self) -> str:
        return "ADB 刷写"

    def tool_tip(self) -> str:
        return "通过 ADB push 将文件刷入设备指定路径"

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("ADB 单刷工具")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #2C3E50;")
        layout.addWidget(title)

        # 环境检测
        env_group = QGroupBox("环境检测")
        env_row = QHBoxLayout(env_group)
        self._env_label = QLabel("未检测")
        self._env_label.setStyleSheet("font-size: 13px;")
        env_row.addWidget(self._env_label)
        env_row.addStretch()
        btn_check = QPushButton("检测环境")
        btn_check.clicked.connect(self._check_env)
        env_row.addWidget(btn_check)
        layout.addWidget(env_group)

        # 文件选择
        file_group = QGroupBox("操作文件")
        file_layout = QVBoxLayout(file_group)
        self._file_info = QLabel("未选择文件")
        self._file_info.setStyleSheet("font-size: 13px; color: #7F8C8D;")
        file_layout.addWidget(self._file_info)

        file_row = QHBoxLayout()
        self._file_combo = QComboBox()
        self._file_combo.setEditable(True)
        self._file_combo.setMinimumWidth(300)
        self._file_combo.currentTextChanged.connect(self._on_file_changed)
        self._load_history(HISTORY_FILE, self._file_combo)
        file_row.addWidget(self._file_combo, 1)
        btn_file = QPushButton("选择文件")
        btn_file.clicked.connect(self._select_file)
        file_row.addWidget(btn_file)
        file_layout.addLayout(file_row)
        layout.addWidget(file_group)

        # 目标路径
        target_group = QGroupBox("目标路径")
        target_row = QHBoxLayout(target_group)
        self._target_combo = QComboBox()
        self._target_combo.setEditable(True)
        self._target_combo.setMinimumWidth(300)
        self._load_history(TARGET_HISTORY_FILE, self._target_combo)
        target_row.addWidget(self._target_combo, 1)
        layout.addWidget(target_group)

        # 操作按钮
        btn_row = QHBoxLayout()
        self._btn_flash = QPushButton("开始刷写")
        self._btn_flash.setStyleSheet("""
            QPushButton { background-color: #E74C3C; color: white; padding: 10px 30px;
                border-radius: 6px; font-size: 14px; font-weight: bold; border: none; }
            QPushButton:hover { background-color: #C0392B; }
            QPushButton:disabled { background-color: #BDC3C7; }
        """)
        self._btn_flash.clicked.connect(self._start_flash)
        btn_row.addWidget(self._btn_flash)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 进度条
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(4)
        self._progress.hide()
        layout.addWidget(self._progress)

        # 输出
        output_group = QGroupBox("操作输出")
        output_layout = QVBoxLayout(output_group)
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setStyleSheet("""
            QTextEdit { background-color: #1E1E1E; color: #D4D4D4; font-family: Consolas;
                font-size: 13px; border: 1px solid #333; border-radius: 4px; padding: 8px; }
        """)
        output_layout.addWidget(self._output)
        layout.addWidget(output_group, 1)

        self._main_layout.addLayout(layout)

    def _check_env(self):
        self._output.clear()
        try:
            p = subprocess.run("adb version", shell=True, capture_output=True, text=True, timeout=5)
            self._env_label.setText("ADB 环境正常")
            self._env_label.setStyleSheet("font-size: 13px; color: green; font-weight: bold;")
            self._output.append(f">>> adb version\n{p.stdout.strip()}")
        except Exception as e:
            self._env_label.setText("ADB 环境异常")
            self._env_label.setStyleSheet("font-size: 13px; color: red; font-weight: bold;")
            self._output.append(f"ERROR: {e}")

    def _select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", "所有文件 (*.*)")
        if path:
            self._file_combo.setCurrentText(path)
            self._update_file_info(path)

    def _on_file_changed(self, text):
        if text and os.path.isfile(text):
            self._update_file_info(text)

    def _update_file_info(self, path):
        fname = os.path.basename(path)
        mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
        self._file_info.setText(f"{fname} - {mtime}")

    def _start_flash(self):
        file_path = self._file_combo.currentText().strip()
        target_path = self._target_combo.currentText().strip()

        if not file_path or not os.path.isfile(file_path):
            QMessageBox.warning(self, "警告", "请先选择有效文件")
            return
        if not target_path:
            QMessageBox.warning(self, "警告", "请输入目标路径")
            return

        self._save_history(HISTORY_FILE, self._file_combo, file_path)
        self._save_history(TARGET_HISTORY_FILE, self._target_combo, target_path)

        self._output.clear()
        self._btn_flash.setEnabled(False)
        self._progress.show()

        self._worker = FlashWorker(file_path, target_path)
        self._worker.output.connect(self._on_output)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_output(self, text):
        self._output.append(text)

    def _on_finished(self, ok, msg):
        self._progress.hide()
        self._btn_flash.setEnabled(True)
        if ok:
            self._output.append(f"\n{msg}")
        else:
            self._output.append(f"\nFAILED: {msg}")
            QMessageBox.critical(self, "错误", f"刷写失败: {msg}")

    def _load_history(self, filename, combo):
        if os.path.exists(filename):
            try:
                with open(filename, "r") as f:
                    data = json.load(f)
                    combo.addItems(data)
            except Exception:
                pass

    def _save_history(self, filename, combo, current):
        items = [combo.itemText(i) for i in range(combo.count())]
        if current in items:
            items.remove(current)
        items.insert(0, current)
        items = items[:10]
        try:
            with open(filename, "w") as f:
                json.dump(items, f)
        except Exception:
            pass