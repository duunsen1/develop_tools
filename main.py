#!/usr/bin/env python3
"""
DevTools - QT 桌面工具集主入口
集合常用开发工具，侧边栏导航，插件式架构
"""

import sys
import os

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QIcon
from PySide6.QtCore import Qt

from qt_demo.main_window import MainWindow
from qt_demo.tools.welcome.widget import WelcomeWidget
from qt_demo.tools.fingerprint_analysis.widget import FingerprintAnalysisWidget
from qt_demo.tools.adb_flash.widget import ADBFlashWidget
from qt_demo.tools.fastboot_flash.widget import FastbootFlashWidget
from qt_demo.tools.log_capture.widget import LogCaptureWidget
from qt_demo.tools.scrcpy.widget import ScrcpyWidget
from qt_demo.tools.quick_cmds.widget import QuickCmdsWidget


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("DevTools")
    app.setApplicationVersion("1.0.0")

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
        ADBFlashWidget(),
        FastbootFlashWidget(),
        LogCaptureWidget(),
        ScrcpyWidget(),
        QuickCmdsWidget(),
    )

    window._sidebar.set_current_index(0)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()