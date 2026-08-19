"""
Fastboot 单刷工具 - PySide6 版本
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
    QProgressBar,
)
from PySide6.QtCore import Qt, Signal, QThread

from ...base_tool_widget import BaseToolWidget
from ...win_proc import CREATE_NO_WINDOW

HISTORY_FILE = "fastboot_file_history.json"

PARTITION_MAP = {
    "boot.img": "boot_a",
    "system.img": "system_a",
    "vendor.img": "vendor_a",
    "vbmeta.img": "vbmeta_a",
    "dtbo.img": "dtbo_a",
    "recovery.img": "recovery",
}


class FastbootWorker(QThread):
    output = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, file_path: str, partition: str):
        super().__init__()
        self._file = file_path
        self._partition = partition

    def run(self):
        try:
            self.output.emit(">>> adb wait-for-device")
            subprocess.run("adb wait-for-device", shell=True, timeout=10, creationflags=CREATE_NO_WINDOW)
            self.output.emit(">>> adb reboot bootloader")
            subprocess.run("adb reboot bootloader", shell=True, timeout=10, creationflags=CREATE_NO_WINDOW)

            self.output.emit("Waiting for fastboot device...")
            for _ in range(30):
                time.sleep(1)
                p = subprocess.run("fastboot devices", shell=True, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
                if "fastboot" in p.stdout:
                    self.output.emit("Fastboot device detected!")
                    break
            else:
                raise RuntimeError("Device did not enter fastboot mode")

            cmd = f"fastboot flash {self._partition} {self._file}"
            self.output.emit(f">>> {cmd}")
            p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120, creationflags=CREATE_NO_WINDOW)
            self.output.emit(p.stdout.strip())
            if p.returncode != 0:
                raise RuntimeError(f"Flash failed: {p.stderr.strip()}")

            self.output.emit(">>> fastboot reboot")
            subprocess.run("fastboot reboot", shell=True, timeout=10, creationflags=CREATE_NO_WINDOW)
            self.output.emit("SUCCESS: Device rebooting!")
            self.finished.emit(True, "刷写完成，设备已重启")
        except Exception as e:
            self.output.emit(f"ERROR: {e}")
            self.finished.emit(False, str(e))


class FastbootFlashWidget(BaseToolWidget):
    def tool_name(self) -> str:
        return "Fastboot 刷写"

    def tool_tip(self) -> str:
        return "通过 Fastboot 刷入镜像文件到设备分区"

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Fastboot 单刷工具")
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
        file_group = QGroupBox("镜像文件")
        file_layout = QVBoxLayout(file_group)
        self._file_info = QLabel("未选择文件")
        self._file_info.setStyleSheet("font-size: 13px; color: #7F8C8D;")
        file_layout.addWidget(self._file_info)

        file_row = QHBoxLayout()
        self._file_combo = QComboBox()
        self._file_combo.setEditable(True)
        self._file_combo.setMinimumWidth(300)
        self._file_combo.currentTextChanged.connect(self._on_file_changed)
        self._load_history()
        file_row.addWidget(self._file_combo, 1)
        btn_file = QPushButton("选择文件")
        btn_file.clicked.connect(self._select_file)
        file_row.addWidget(btn_file)
        file_layout.addLayout(file_row)
        layout.addWidget(file_group)

        # 分区信息
        info_group = QGroupBox("分区信息")
        info_row = QHBoxLayout(info_group)
        self._partition_label = QLabel("自动识别分区: 未选择")
        self._partition_label.setStyleSheet("font-size: 13px; color: #7F8C8D;")
        info_row.addWidget(self._partition_label)
        info_row.addStretch()
        layout.addWidget(info_group)

        # 操作按钮
        btn_row = QHBoxLayout()
        self._btn_flash = QPushButton("刷入分区")
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
            p = subprocess.run("adb version", shell=True, capture_output=True, text=True, timeout=5, creationflags=CREATE_NO_WINDOW)
            self._output.append(f">>> adb version\n{p.stdout.strip()}")
            p = subprocess.run("fastboot --version", shell=True, capture_output=True, text=True, timeout=5, creationflags=CREATE_NO_WINDOW)
            self._output.append(f">>> fastboot --version\n{p.stdout.strip()}")
            self._env_label.setText("环境正常")
            self._env_label.setStyleSheet("font-size: 13px; color: green; font-weight: bold;")
        except Exception as e:
            self._env_label.setText("环境异常")
            self._env_label.setStyleSheet("font-size: 13px; color: red; font-weight: bold;")
            self._output.append(f"ERROR: {e}")

    def _select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择镜像文件", "", "镜像文件 (*.img);;所有文件 (*.*)")
        if path:
            self._file_combo.setCurrentText(path)
            self._on_file_changed(path)

    def _on_file_changed(self, text):
        if text and os.path.isfile(text):
            fname = os.path.basename(text)
            mtime = datetime.fromtimestamp(os.path.getmtime(text)).strftime("%Y-%m-%d %H:%M:%S")
            self._file_info.setText(f"{fname} - {mtime}")
            partition = PARTITION_MAP.get(fname.lower(), "未知")
            self._partition_label.setText(f"自动识别分区: {partition}")
            self._partition_label.setStyleSheet(
                "font-size: 13px; color: green; font-weight: bold;" if partition != "未知"
                else "font-size: 13px; color: red; font-weight: bold;"
            )

    def _start_flash(self):
        file_path = self._file_combo.currentText().strip()
        if not file_path or not os.path.isfile(file_path):
            QMessageBox.warning(self, "警告", "请先选择有效镜像文件")
            return

        fname = os.path.basename(file_path).lower()
        partition = PARTITION_MAP.get(fname)
        if not partition:
            QMessageBox.critical(self, "错误", f"无法识别 {fname} 对应的分区！\n已知: {list(PARTITION_MAP.keys())}")
            return

        self._save_history(file_path)
        self._output.clear()
        self._btn_flash.setEnabled(False)
        self._progress.show()

        self._worker = FastbootWorker(file_path, partition)
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

    def _load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r") as f:
                    for item in json.load(f):
                        self._file_combo.addItem(item)
            except Exception:
                pass

    def _save_history(self, current):
        items = [self._file_combo.itemText(i) for i in range(self._file_combo.count())]
        if current in items:
            items.remove(current)
        items.insert(0, current)
        items = items[:10]
        try:
            with open(HISTORY_FILE, "w") as f:
                json.dump(items, f)
        except Exception:
            pass