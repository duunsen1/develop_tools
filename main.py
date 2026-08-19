#!/usr/bin/env python3
"""
DevTools - QT 桌面工具集主入口
集合常用开发工具，侧边栏导航，插件式架构
"""

import sys
import os
import logging
import time

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QIcon
from PySide6.QtCore import Qt, QTimer

from qt_demo.app_log import setup_logging, install_excepthook, start_watchdog
from qt_demo.main_window import MainWindow
from qt_demo.tools.welcome.widget import WelcomeWidget
from qt_demo.tools.fingerprint_analysis.widget import FingerprintAnalysisWidget
from qt_demo.tools.fp_dump.widget import FpDumpWidget
from qt_demo.tools.adb_flash.widget import ADBFlashWidget
from qt_demo.tools.fastboot_flash.widget import FastbootFlashWidget
from qt_demo.tools.log_capture.widget import LogCaptureWidget
from qt_demo.tools.scrcpy.widget import ScrcpyWidget
from qt_demo.tools.quick_cmds.widget import QuickCmdsWidget
from qt_demo.tools.workspace.widget import WorkspaceWidget
from qt_demo.tools.jira_board.widget import JiraBoardWidget


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("DevTools")
    app.setApplicationVersion("1.0.0")

    # 日志 + 未捕获异常 + 主线程卡死监控
    log_path = setup_logging()
    install_excepthook()
    logger = logging.getLogger("devtools")
    logger.info("DevTools 启动，日志: %s", log_path)

    heartbeat = [time.time()]
    heartbeat_timer = QTimer()
    heartbeat_timer.timeout.connect(lambda: heartbeat.__setitem__(0, time.time()))
    heartbeat_timer.start(1000)
    watchdog = start_watchdog(heartbeat)

    # 窗口图标：兼容源码运行和 PyInstaller 打包
    if getattr(sys, "frozen", False):
        icon_path = os.path.join(os.path.dirname(sys.executable), "_internal", "assets", "devtools.ico")
    else:
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "devtools.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    font = QFont("Microsoft YaHei UI", 10)
    app.setFont(font)

    app.setStyleSheet("""
        QToolTip {
            background-color: #2C3E50;
            color: white;
            border: 1px solid #34495E;
            padding: 5px;
            border-radius: 4px;
            font-size: 12px;
        }
    """)

    window = MainWindow()

    window.register_tools(
        WelcomeWidget(),
        FingerprintAnalysisWidget(),
        FpDumpWidget(),
        ADBFlashWidget(),
        FastbootFlashWidget(),
        LogCaptureWidget(),
        ScrcpyWidget(),
        QuickCmdsWidget(),
        WorkspaceWidget(),
        JiraBoardWidget(),
    )

    window._sidebar.set_current_index(0)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()