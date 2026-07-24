#!/usr/bin/env python3
"""
DevTools - QT 桌面工具集主入口
集合常用开发工具，侧边栏导航，插件式架构
"""

import sys
import os

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

from qt_demo.main_window import MainWindow
from qt_demo.tools.welcome.widget import WelcomeWidget
from qt_demo.tools.fingerprint_analysis.widget import FingerprintAnalysisWidget


def main():
    # 启用高 DPI 缩放
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("DevTools")
    app.setApplicationVersion("1.0.0")

    # 设置全局字体
    font = QFont("Microsoft YaHei UI", 10)
    app.setFont(font)

    # 全局样式表
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

    # 创建主窗口
    window = MainWindow()

    # 注册工具
    window.register_tools(
        WelcomeWidget(),           # 首页
        FingerprintAnalysisWidget(),  # 指纹解锁速度分析
    )

    # 切换到首页
    window._sidebar.set_current_index(0)

    # 显示窗口
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()