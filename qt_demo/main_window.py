"""
主窗口 - 侧边栏 + QStackedWidget 布局
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QStackedWidget,
    QStatusBar, QApplication,
)
from PySide6.QtCore import Qt, QSize
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
        self._tools = []  # [(name, widget), ...]
        self._setup_window()
        self._setup_ui()

    def _setup_window(self):
        self.setWindowTitle(self.APP_TITLE)
        self.setMinimumSize(900, 600)
        self.resize(self.APP_WIDTH, self.APP_HEIGHT)

        # 全局样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #F5F6FA;
            }
        """)

    def _setup_ui(self):
        # 中央部件
        central = QWidget()
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 侧边栏
        self._sidebar = Sidebar()
        self._sidebar.tool_changed.connect(self._on_tool_changed)
        layout.addWidget(self._sidebar)

        # 右侧内容区
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("""
            QStackedWidget {
                background-color: #F5F6FA;
            }
        """)
        layout.addWidget(self._stack, 1)

        # 状态栏
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
        self._status.showMessage("就绪")

    def register_tool(self, widget: BaseToolWidget):
        """注册一个工具到侧边栏和内容区"""
        name = widget.tool_name()
        icon = widget.tool_icon()
        tip = getattr(widget, 'tool_tip', lambda: "")()
        self._sidebar.add_tool(name, icon, tip)
        self._stack.addWidget(widget)
        self._tools.append((name, widget))

    def register_tools(self, *widgets: BaseToolWidget):
        """批量注册工具"""
        for w in widgets:
            self.register_tool(w)

    def _on_tool_changed(self, index: int):
        """切换工具"""
        if 0 <= index < len(self._tools):
            # 停用当前工具
            current = self._stack.currentWidget()
            if isinstance(current, BaseToolWidget):
                current.on_deactivate()

            # 切换到新工具
            self._stack.setCurrentIndex(index)
            name, widget = self._tools[index]
            self._status.showMessage(f"当前工具: {name}")
            widget.on_activate()

    def set_status(self, message: str, timeout: int = 5000):
        """设置状态栏消息"""
        self._status.showMessage(message, timeout)