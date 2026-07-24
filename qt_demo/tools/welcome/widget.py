"""
欢迎首页 - 显示工具概览和快速入口
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGridLayout, QFrame,
    QSizePolicy, QPushButton,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QPixmap

from ...base_tool_widget import BaseToolWidget


class WelcomeWidget(BaseToolWidget):
    """欢迎首页"""

    def tool_name(self) -> str:
        return "首页"

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        # 标题
        title = QLabel("🔧 DevTools")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 36px;
            font-weight: bold;
            color: #2C3E50;
            margin: 20px 0px;
        """)
        layout.addWidget(title)

        # 副标题
        subtitle = QLabel("开发工具集 · 集合常用工具，提高工作效率")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("""
            font-size: 16px;
            color: #7F8C8D;
            margin-bottom: 30px;
        """)
        layout.addWidget(subtitle)

        # 工具卡片网格
        grid = QGridLayout()
        grid.setSpacing(20)
        grid.setAlignment(Qt.AlignCenter)

        tools_info = [
            ("🔍", "指纹解锁速度分析", "分析 Android 指纹解锁日志，统计解锁时间并生成 Excel 报告"),
            ("📦", "更多工具即将上线", "正在开发中，敬请期待..."),
        ]

        for i, (icon, name, desc) in enumerate(tools_info):
            card = self._create_card(icon, name, desc)
            grid.addWidget(card, i // 2, i % 2)

        layout.addLayout(grid)
        layout.addStretch()

        self._main_layout.addLayout(layout)

    def _create_card(self, icon: str, name: str, desc: str) -> QFrame:
        card = QFrame()
        card.setFixedSize(360, 160)
        card.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #E8ECF1;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        lbl_icon = QLabel(icon)
        lbl_icon.setStyleSheet("font-size: 32px;")
        layout.addWidget(lbl_icon)

        lbl_name = QLabel(name)
        lbl_name.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #2C3E50;
        """)
        layout.addWidget(lbl_name)

        lbl_desc = QLabel(desc)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("""
            font-size: 13px;
            color: #7F8C8D;
            line-height: 1.4;
        """)
        layout.addWidget(lbl_desc)

        return card