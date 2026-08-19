"""
主窗口 - 侧边栏 + QStackedWidget 布局 + ADB/Fastboot 状态
"""

import logging
import subprocess
import time

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QStackedWidget,
    QStatusBar, QApplication, QLabel, QPushButton,
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QFont

from .sidebar import Sidebar
from .base_tool_widget import BaseToolWidget
from .win_proc import CREATE_NO_WINDOW

logger = logging.getLogger("devtools")


class MainWindow(QMainWindow):
    """QT 工具集主窗口"""

    APP_TITLE = "DevTools - 开发工具集"
    APP_WIDTH = 1200
    APP_HEIGHT = 800

    def __init__(self):
        super().__init__()
        self._tools = []
        self._last_dev_err_log = 0.0
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

        # 重启设备按钮（常驻状态栏，随手可点）
        self._btn_reboot = QPushButton("↻ 重启设备")
        self._btn_reboot.setStyleSheet("""
            QPushButton {
                background-color: #E67E22; color: white; font-weight: bold;
                border: none; border-radius: 4px; padding: 4px 14px; font-size: 12px;
            }
            QPushButton:hover { background-color: #CA6F1E; }
            QPushButton:disabled { background-color: #BDC3C7; }
        """)
        self._btn_reboot.clicked.connect(self._reboot_device)
        self._status.addPermanentWidget(self._btn_reboot)

        self._status.showMessage("就绪")

    def _start_device_monitor(self):
        self._check_devices()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_devices)
        self._timer.start(2000)

    def _probe_device(self, args, timeout=2):
        """探测 adb/fastboot 是否可用。用列表参数（不用 shell），
        避免 Windows 下超时杀外壳后子进程残留攥住管道导致主线程卡死。"""
        try:
            p = subprocess.run(
                args, capture_output=True, text=True, timeout=timeout,
                creationflags=CREATE_NO_WINDOW,
            )
            return p
        except Exception:
            now = time.time()
            if now - self._last_dev_err_log > 30:
                logger.warning("设备探测异常: %s", args, exc_info=True)
                self._last_dev_err_log = now
            raise

    def _check_devices(self):
        # ADB
        adb_ok = False
        try:
            p = self._probe_device(["adb", "devices"])
            if p.returncode == 0:
                devices = [l for l in p.stdout.splitlines()[1:] if l.strip() and "\tdevice" in l]
                adb_ok = bool(devices)
        except Exception:
            pass
        self._lbl_adb.setText("ADB: Y" if adb_ok else "ADB: N")
        self._lbl_adb.setStyleSheet("font-size: 12px; font-weight: bold; color: green; padding: 0 10px;" if adb_ok else "font-size: 12px; font-weight: bold; color: red; padding: 0 10px;")

        # Fastboot
        fastboot_ok = False
        try:
            p = self._probe_device(["fastboot", "devices"])
            if p.returncode == 0 and "fastboot" in p.stdout:
                fastboot_ok = True
        except Exception:
            pass
        self._lbl_fastboot.setText("Fastboot: Y" if fastboot_ok else "Fastboot: N")
        self._lbl_fastboot.setStyleSheet("font-size: 12px; font-weight: bold; color: green; padding: 0 10px;" if fastboot_ok else "font-size: 12px; font-weight: bold; color: red; padding: 0 10px;")

    def _reboot_device(self):
        """重启设备 (adb reboot)"""
        self._btn_reboot.setEnabled(False)
        self._status.showMessage("正在重启设备...", 0)
        logger.info("请求重启设备")
        try:
            p = subprocess.run(["adb", "reboot"], capture_output=True, text=True, timeout=10, creationflags=CREATE_NO_WINDOW)
            if p.returncode == 0:
                self._status.showMessage("设备重启中，稍后自动恢复连接", 8000)
                logger.info("adb reboot 已发送")
            else:
                self._status.showMessage(f"重启失败: {p.stderr.strip() or 'adb 返回非零'}", 5000)
                logger.warning("adb reboot 失败: %s", p.stderr.strip())
        except subprocess.TimeoutExpired:
            self._status.showMessage("重启命令超时（设备可能已断开）", 5000)
            logger.warning("adb reboot 超时")
        except Exception as e:
            self._status.showMessage(f"重启出错: {e}", 5000)
            logger.error("adb reboot 出错: %s", e)
        self._btn_reboot.setEnabled(True)

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
            logger.info("切换到工具: %s", name)
            self._status.showMessage(f"当前工具: {name}")
            widget.on_activate()

    def set_status(self, message: str, timeout: int = 5000):
        self._status.showMessage(message, timeout)