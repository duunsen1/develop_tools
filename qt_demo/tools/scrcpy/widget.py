"""
Scrcpy 投屏工具 - PySide6 版本
"""

import os
import subprocess

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QTextEdit, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QThread

from ...base_tool_widget import BaseToolWidget
from ...win_proc import CREATE_NO_WINDOW


class ScrcpyWidget(BaseToolWidget):
    def tool_name(self) -> str:
        return "投屏 (Scrcpy)"

    def tool_tip(self) -> str:
        return "启动 scrcpy 投屏，将安卓设备屏幕投射到 PC"

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Scrcpy 投屏")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #2C3E50;")
        layout.addWidget(title)

        desc = QLabel("将 Android 设备屏幕投射到 PC，支持 USB 和无线连接")
        desc.setStyleSheet("font-size: 13px; color: #7F8C8D;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 设备检测
        dev_group = QGroupBox("设备状态")
        dev_row = QHBoxLayout(dev_group)
        self._dev_label = QLabel("未检测")
        self._dev_label.setStyleSheet("font-size: 14px;")
        dev_row.addWidget(self._dev_label)
        dev_row.addStretch()
        btn_check = QPushButton("检测设备")
        btn_check.clicked.connect(self._check_device)
        dev_row.addWidget(btn_check)
        layout.addWidget(dev_group)

        # 启动按钮
        btn_row = QHBoxLayout()
        self._btn_start = QPushButton("启动投屏")
        self._btn_start.setStyleSheet("""
            QPushButton { background-color: #27AE60; color: white; padding: 15px 50px;
                border-radius: 8px; font-size: 16px; font-weight: bold; border: none; }
            QPushButton:hover { background-color: #219A52; }
            QPushButton:disabled { background-color: #BDC3C7; }
        """)
        self._btn_start.clicked.connect(self._start_scrcpy)
        btn_row.addWidget(self._btn_start)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 输出
        output_group = QGroupBox("运行日志")
        output_layout = QVBoxLayout(output_group)
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setStyleSheet("""
            QTextEdit { background-color: #1E1E1E; color: #D4D4D4; font-family: Consolas;
                font-size: 13px; border: 1px solid #333; border-radius: 4px; padding: 8px; }
        """)
        output_layout.addWidget(self._output)
        layout.addWidget(output_group, 1)

        layout.addStretch()
        self._main_layout.addLayout(layout)

    def _check_device(self):
        self._output.clear()
        try:
            p = subprocess.run("adb devices", shell=True, capture_output=True, text=True, timeout=5, creationflags=CREATE_NO_WINDOW)
            self._output.append(f">>> adb devices\n{p.stdout}")
            lines = [l for l in p.stdout.splitlines()[1:] if l.strip() and "\tdevice" in l]
            if lines:
                self._dev_label.setText(f"已连接 {len(lines)} 台设备")
                self._dev_label.setStyleSheet("font-size: 14px; color: green; font-weight: bold;")
            else:
                self._dev_label.setText("未检测到设备")
                self._dev_label.setStyleSheet("font-size: 14px; color: red; font-weight: bold;")
        except Exception as e:
            self._dev_label.setText("ADB 不可用")
            self._dev_label.setStyleSheet("font-size: 14px; color: red; font-weight: bold;")
            self._output.append(f"ERROR: {e}")

    def _start_scrcpy(self):
        # 查找 scrcpy
        script_dir = os.path.dirname(os.path.abspath(__file__))
        scrcpy_dir = os.path.join(script_dir, "scrcpy")
        scrcpy_exe = os.path.join(scrcpy_dir, "scrcpy.exe")

        if not os.path.exists(scrcpy_exe):
            QMessageBox.critical(self, "程序缺失", f"未找到投屏程序: {scrcpy_exe}")
            return

        self._output.clear()
        self._output.append(">>> Checking devices...")

        try:
            default_adb = os.path.join(scrcpy_dir, "adb.exe")
            adb_path = default_adb if os.path.exists(default_adb) else "adb"
            p = subprocess.run([adb_path, "devices"], capture_output=True, text=True, check=True, creationflags=CREATE_NO_WINDOW)
            devices = [l.split("\t")[0] for l in p.stdout.splitlines()[1:] if "\tdevice" in l]
            if not devices:
                self._output.append("ERROR: No device connected!")
                QMessageBox.critical(self, "设备未连接", "未检测到安卓设备！")
                return
        except Exception as e:
            self._output.append(f"ERROR: {e}")
            QMessageBox.critical(self, "ADB 错误", "ADB 执行失败，请检查设备连接")
            return

        try:
            self._output.append(f">>> Starting scrcpy for {len(devices)} device(s)...")
            subprocess.Popen([scrcpy_exe], cwd=scrcpy_dir, creationflags=CREATE_NO_WINDOW)
            self._output.append("Scrcpy started! Check device for authorization prompt.")
            QMessageBox.information(self, "投屏启动", "投屏程序已启动，请查看设备授权提示！")
        except Exception as e:
            self._output.append(f"ERROR: {e}")
            QMessageBox.critical(self, "启动失败", f"投屏启动失败: {e}")