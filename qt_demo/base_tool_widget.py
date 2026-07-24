"""
工具基类 - 所有工具插件必须继承 BaseToolWidget
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon


class BaseToolWidget(QWidget):
    """工具插件基类，所有工具需实现以下接口"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._setup_ui()

    def tool_name(self) -> str:
        """返回工具名称，显示在侧边栏"""
        raise NotImplementedError

    def tool_icon(self):
        """返回工具图标，显示在侧边栏（可选）"""
        return None

    def tool_tip(self) -> str:
        """返回工具提示文本"""
        return ""

    def _setup_ui(self):
        """子类在此构建 UI，基类中为空白实现"""
        pass

    def on_activate(self):
        """当工具被选中时调用（可用于刷新数据等）"""
        pass

    def on_deactivate(self):
        """当切换到其他工具时调用"""
        pass