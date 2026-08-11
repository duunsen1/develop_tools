"""
主窗口 - 侧边栏 + QStackedWidget 布局 + ADB/Fastboot 状态
"""

import subprocess

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QStackedWidget,
    QStatusBar, QApplication, QLabel,
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QFont

from .sidebar import Sidebar
from .base_tool_widget import BaseToolWidget


class MainWindow(QMainWindow):
    """QT 工具集主窗口"""

    APP_TITLE = "DevTools - 开发工具集"
    APP_WIDTH = 1200
    APP_HEIGHT = 800

    def __init__(self):
        super().__init__()
        self._tools = []
        self._setup_window()
        self._setup_ui()
        self._start_device_monitor()

    def _setup_window(self):
        self.setWindowTitle(self.APP_TITLE)
        self.setMinimumSize(900, 600)
        self.resize(self.APP_WIDTH, self.APP_HEIGHT)
        self.setStyleSheet("QMainWindow { background-color: #F5F6FA; }")

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._sidebar = Sidebar()
        self._sidebar.tool_changed.connect(self._on_tool_changed)
        layout.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("QStackedWidget { background-color: #F5F6FA; }")
        layout.addWidget(self._stack, 1)

        self._status = QStatusBar()
        self._status.setStyleSheet("""
            QStatusBar {
                background-color: #ECF0F1;
                border-top: 1px solid #BDC3C7;
                font-size: 12px;
                padding: 2px 10px;
            }
        """)
        self.setStatusBar(self._status)

        # ADB 状态标签
        self._lbl_adb = QLabel("ADB: N")
        self._lbl_adb.setStyleSheet("font-size: 12px; font-weight: bold; color: red; padding: 0 10px;")
        self._status.addPermanentWidget(self._lbl_adb)

        # Fastboot 状态标签
        self._lbl_fastboot = QLabel("Fastboot: N")
        self._lbl_fastboot.setStyleSheet("font-size: 12px; font-weight: bold; color: red; padding: 0 10px;")
        self._status.addPermanentWidget(self._lbl_fastboot)

        self._status.showMessage("就绪")

    def _start_device_monitor(self):
        self._check_devices()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_devices)
        self._timer.start(2000)

    def _check_devices(self):
        # ADB
        try:
            p = subprocess.run("adb devices", shell=True, capture_output=True, text=True, timeout=2)
            if p.returncode == 0:
                devices = [l for l in p.stdout.splitlines()[1:] if l.strip() and "\tdevice" in l]
                if devices:
                    self._lbl_adb.setText("ADB: Y")
                    self._lbl_adb.setStyleSheet("font-size: 12px; font-weight: bold; color: green; padding: 0 10px;")
                else:
                    self._lbl_adb.setText("ADB: N")
                    self._lbl_adb.setStyleSheet("font-size: 12px; font-weight: bold; color: red; padding: 0 10px;")
            else:
                raise Exception("adb failed")
        except Exception:
            self._lbl_adb.setText("ADB: N")
            self._lbl_adb.setStyleSheet("font-size: 12px; font-weight: bold; color: red; padding: 0 10px;")

        # Fastboot
        try:
            p = subprocess.run("fastboot devices", shell=True, capture_output=True, text=True, timeout=2)
            if p.returncode == 0 and "fastboot" in p.stdout:
                self._lbl_fastboot.setText("Fastboot: Y")
                self._lbl_fastboot.setStyleSheet("font-size: 12px; font-weight: bold; color: green; padding: 0 10px;")
            else:
                self._lbl_fastboot.setText("Fastboot: N")
                self._lbl_fastboot.setStyleSheet("font-size: 12px; font-weight: bold; color: red; padding: 0 10px;")
        except Exception:
            self._lbl_fastboot.setText("Fastboot: N")
            self._lbl_fastboot.setStyleSheet("font-size: 12px; font-weight: bold; color: red; padding: 0 10px;")

    def register_tool(self, widget: BaseToolWidget):
        name = widget.tool_name()
        icon = widget.tool_icon()
        tip = getattr(widget, 'tool_tip', lambda: "")()
        self._sidebar.add_tool(name, icon, tip)
        self._stack.addWidget(widget)
        self._tools.append((name, widget))

    def register_tools(self, *widgets: BaseToolWidget):
        for w in widgets:
            self.register_tool(w)

    def _on_tool_changed(self, index: int):
        if 0 <= index < len(self._tools):
            current = self._stack.currentWidget()
            if isinstance(current, BaseToolWidget):
                current.on_deactivate()
            self._stack.setCurrentIndex(index)
            name, widget = self._tools[index]
            self._status.showMessage(f"当前工具: {name}")
            widget.on_activate()

    def set_status(self, message: str, timeout: int = 5000):
        self._status.showMessage(message, timeout)