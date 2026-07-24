"""
侧边栏导航组件
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QColor, QIcon, QPalette


class Sidebar(QWidget):
    """侧边栏导航组件，支持图标+文字列表"""

    # 信号：切换工具（索引）
    tool_changed = Signal(int)

    # 配色
    BG_COLOR = "#2C3E50"
    TEXT_COLOR = "#ECF0F1"
    ACTIVE_BG = "#3498DB"
    HOVER_BG = "#34495E"
    HEADER_COLOR = "#1ABC9C"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(220)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # 顶部标题区
        self._header = QLabel("🔧 DevTools")
        self._header.setAlignment(Qt.AlignCenter)
        self._header.setFixedHeight(60)
        self._header.setStyleSheet(f"""
            QLabel {{
                color: {self.HEADER_COLOR};
                font-size: 18px;
                font-weight: bold;
                background-color: {self.BG_COLOR};
                padding: 10px;
            }}
        """)
        self._layout.addWidget(self._header)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {self.ACTIVE_BG};")
        sep.setFixedHeight(1)
        self._layout.addWidget(sep)

        # 工具列表
        self._list = QListWidget()
        self._list.setFrameShape(QFrame.NoFrame)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self._list.setSpacing(2)
        self._list.setStyleSheet(f"""
            QListWidget {{
                background-color: {self.BG_COLOR};
                border: none;
                outline: none;
                padding: 5px 0px;
            }}
            QListWidget::item {{
                color: {self.TEXT_COLOR};
                padding: 12px 20px;
                font-size: 14px;
                border-radius: 0px;
            }}
            QListWidget::item:hover {{
                background-color: {self.HOVER_BG};
            }}
            QListWidget::item:selected {{
                background-color: {self.ACTIVE_BG};
                color: white;
            }}
        """)
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._layout.addWidget(self._list)

        # 底部版本信息
        self._footer = QLabel("v1.0.0\nPySide6 Demo")
        self._footer.setAlignment(Qt.AlignCenter)
        self._footer.setFixedHeight(50)
        self._footer.setStyleSheet(f"""
            QLabel {{
                color: #7F8C8D;
                font-size: 11px;
                background-color: {self.BG_COLOR};
                padding: 5px;
            }}
        """)
        self._layout.addWidget(self._footer)

        # 背景色
        self.setStyleSheet(f"QWidget#Sidebar {{ background-color: {self.BG_COLOR}; }}")

    def add_tool(self, name: str, icon=None, tip: str = ""):
        """添加一个工具项到侧边栏"""
        item = QListWidgetItem()
        item.setText(name)
        item.setToolTip(tip or name)
        item.setSizeHint(QSize(220, 44))
        self._list.addItem(item)
        return item

    def set_current_index(self, index: int):
        """切换到指定索引的工具"""
        if 0 <= index < self._list.count():
            self._list.setCurrentRow(index)

    def current_index(self) -> int:
        return self._list.currentRow()

    def _on_row_changed(self, row: int):
        if row >= 0:
            self.tool_changed.emit(row)