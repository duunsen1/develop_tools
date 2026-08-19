"""
工作区（看板） - 管理开发事项：标签 / 可编辑主题 / 四种状态 / 详情编辑
"""

import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox,
    QLineEdit, QScrollArea, QFrame, QMenu, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, QMimeData
from PySide6.QtGui import QDrag

from ...base_tool_widget import BaseToolWidget
from .models import STATUSES, STATUS_COLORS, tag_color, Item, new_id
from .storage import load_data, save_data
from .dialogs import ItemDialog, TagManagerDialog

MIME_ITEM = "application/x-devtools-item"


class WorkspaceWidget(BaseToolWidget):
    """工作区看板工具"""

    def tool_name(self) -> str:
        return "任务清单"

    def tool_tip(self) -> str:
        return "清单式管理开发事项：标签、状态、详情"

    def _setup_ui(self):
        self.tags, self.items = load_data()
        self._tag_filter = ""
        self._search = ""

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 顶部工具条
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        btn_add = QPushButton("＋ 新增事项")
        btn_add.setStyleSheet(self._toolbar_btn_style("#3498DB"))
        btn_add.clicked.connect(self._add_item)
        toolbar.addWidget(btn_add)

        btn_tags = QPushButton("管理标签")
        btn_tags.setStyleSheet(self._toolbar_btn_style("#2C3E50"))
        btn_tags.clicked.connect(self._manage_tags)
        toolbar.addWidget(btn_tags)

        toolbar.addStretch()

        lbl_filter = QLabel("筛选:")
        lbl_filter.setStyleSheet("font-size: 13px; color: #7F8C8D;")
        toolbar.addWidget(lbl_filter)

        self._filter_combo = QComboBox()
        self._filter_combo.setMinimumWidth(120)
        self._filter_combo.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self._filter_combo)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索主题…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setFixedWidth(180)
        self._search_edit.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self._search_edit)

        layout.addLayout(toolbar)

        # 看板区
        self._board_scroll = QScrollArea()
        self._board_scroll.setWidgetResizable(True)
        self._board_scroll.setFrameShape(QFrame.NoFrame)
        self._board_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._board_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._board_scroll.setStyleSheet("QScrollArea { background: transparent; }")

        board = QWidget()
        board_layout = QHBoxLayout(board)
        board_layout.setContentsMargins(4, 4, 4, 4)
        board_layout.setSpacing(12)
        self._columns = {}
        for status in STATUSES:
            column = StatusColumn(status, self)
            self._columns[status] = column
            board_layout.addWidget(column)
        self._board_scroll.setWidget(board)
        layout.addWidget(self._board_scroll, 1)

        self._main_layout.addLayout(layout)

        self._refresh_tag_combo()
        self._render()

    @staticmethod
    def _toolbar_btn_style(bg):
        return f"""
            QPushButton {{ background-color: {bg}; color: white; border: none;
                border-radius: 4px; padding: 7px 16px; font-size: 13px; font-weight: bold; }}
            QPushButton:hover {{ opacity: 0.9; }}
        """

    # ---------- 数据操作 ----------

    def _find_item(self, item_id):
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def _save(self):
        save_data(self.tags, self.items)

    def _render(self):
        for status in STATUSES:
            column = self._columns[status]
            cards = []
            for item in self.items:
                if item.status != status:
                    continue
                if not self._matches_filter(item):
                    continue
                cards.append(ItemCard(self, item))
            column.set_items(cards)
        self._refresh_tag_combo()

    def _matches_filter(self, item):
        if self._tag_filter and self._tag_filter not in item.tags:
            return False
        if self._search and self._search not in item.title:
            return False
        return True

    def _refresh_tag_combo(self):
        current = self._filter_combo.currentText()
        self._filter_combo.blockSignals(True)
        self._filter_combo.clear()
        self._filter_combo.addItem("全部标签", "")
        for tag in self.tags:
            self._filter_combo.addItem(f"#{tag}", tag)
        if current in self.tags:
            self._filter_combo.setCurrentText(current)
        else:
            self._filter_combo.setCurrentIndex(0)
        self._tag_filter = self._filter_combo.currentData() or ""
        self._filter_combo.blockSignals(False)

    def _on_filter_changed(self, _text):
        self._tag_filter = self._filter_combo.currentData() or ""
        self._render()

    def _on_search_changed(self, text):
        self._search = text.strip()
        self._render()

    # ---------- 事项操作 ----------

    def _add_item(self):
        default_tags = [self._tag_filter] if self._tag_filter else []
        dlg = ItemDialog(self.tags, parent=self)
        if default_tags:
            for cb in dlg._tag_checks:
                cb.setChecked(cb.text() in default_tags)
        if dlg.exec_() != ItemDialog.Accepted:
            return
        title, status, tags, detail = dlg.result_fields()
        item = Item(id=new_id(), title=title, detail=detail, status=status, tags=tags)
        self.items.append(item)
        self._save()
        self._render()

    def _open_detail(self, item_id):
        item = self._find_item(item_id)
        if not item:
            return
        dlg = ItemDialog(self.tags, item, parent=self)
        if dlg.exec_() != ItemDialog.Accepted:
            return
        title, status, tags, detail = dlg.result_fields()
        item.title = title
        item.status = status
        item.tags = tags
        item.detail = detail
        item.updated = time.time()
        self._save()
        self._render()

    def rename_item(self, item_id, new_title):
        item = self._find_item(item_id)
        if not item:
            return
        item.title = new_title
        self._save()
        self._render()

    def move_item(self, item_id, new_status):
        item = self._find_item(item_id)
        if not item or item.status == new_status:
            return
        item.status = new_status
        self._save()
        self._render()

    def delete_item(self, item_id):
        item = self._find_item(item_id)
        if not item:
            return
        ret = QMessageBox.question(
            self, "删除事项", f"确定删除事项「{item.title}」？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        self.items.remove(item)
        self._save()
        self._render()

    def _manage_tags(self):
        dlg = TagManagerDialog(self.tags, self.items, parent=self)
        if dlg.exec_() != TagManagerDialog.Accepted:
            return
        new_tags = dlg.get_tags()
        renames = dlg.get_renames()
        if renames:
            for item in self.items:
                item.tags = [renames.get(t, t) for t in item.tags]
        removed = set(self.tags) - set(new_tags)
        if removed:
            for item in self.items:
                item.tags = [t for t in item.tags if t not in removed]
        self.tags = new_tags
        self._save()
        self._render()


class StatusColumn(QFrame):
    """看板中的一列，代表一种状态，是拖拽放置的目标"""

    def __init__(self, status, workspace, parent=None):
        super().__init__(parent)
        self._status = status
        self._workspace = workspace
        self.setFixedWidth(260)
        self.setAcceptDrops(True)
        self.setObjectName("StatusColumn")
        self.setStyleSheet(f"""
            QFrame#StatusColumn {{
                background-color: #EDF0F3; border: 1px solid #E0E4E8;
                border-radius: 10px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 列头
        header = QHBoxLayout()
        header.setSpacing(6)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {STATUS_COLORS[self._status]}; font-size: 12px;")
        header.addWidget(dot)
        self._count_label = QLabel(self._status)
        self._count_label.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {STATUS_COLORS[self._status]};"
        )
        header.addWidget(self._count_label)
        header.addStretch()
        layout.addLayout(header)

        # 卡片滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        content = QWidget()
        self._cards_layout = QVBoxLayout(content)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(8)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

    def set_items(self, cards):
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        for card in cards:
            self._cards_layout.addWidget(card)
        self._cards_layout.addStretch(1)
        self._count_label.setText(f"{self._status}  {len(cards)}")

    # 拖拽放置
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_ITEM):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(MIME_ITEM):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(MIME_ITEM):
            event.ignore()
            return
        item_id = bytes(event.mimeData().data(MIME_ITEM)).decode("utf-8")
        # 延迟到拖拽结束后再刷新，避免拖拽源控件被提前销毁
        QTimer.singleShot(0, lambda: self._workspace.move_item(item_id, self._status))
        event.acceptProposedAction()


class ItemCard(QFrame):
    """看板卡片：单击开详情、双击行内改名、可拖拽"""

    def __init__(self, workspace, item, parent=None):
        super().__init__(parent)
        self._workspace = workspace
        self._item_id = item.id
        self._renaming = False
        self._dragging = False
        self._press_pos = None
        self._suppress_release = False
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(lambda: self._workspace._open_detail(self._item_id))

        self.setObjectName("ItemCard")
        self.setStyleSheet("""
            QFrame#ItemCard {
                background-color: white; border: 1px solid #E8ECF1;
                border-radius: 8px;
            }
            QFrame#ItemCard:hover { border: 1px solid #3498DB; }
        """)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        self._title_label = QLabel(item.title)
        self._title_label.setWordWrap(True)
        self._title_label.setStyleSheet("""
            font-size: 13px; font-weight: bold; color: #2C3E50; border: none;
            background: transparent;
        """)
        self._title_layout = QVBoxLayout()
        self._title_layout.setContentsMargins(0, 0, 0, 0)
        self._title_layout.addWidget(self._title_label)
        layout.addLayout(self._title_layout)

        if item.tags:
            tags_row = QHBoxLayout()
            tags_row.setContentsMargins(0, 0, 0, 0)
            tags_row.setSpacing(4)
            for tag in item.tags[:4]:
                chip = QLabel(tag)
                color = tag_color(tag)
                chip.setStyleSheet(f"""
                    background-color: {color}; color: white; border-radius: 3px;
                    padding: 1px 7px; font-size: 10px; font-weight: bold;
                """)
                tags_row.addWidget(chip)
            tags_row.addStretch()
            layout.addLayout(tags_row)

    @property
    def item_id(self):
        return self._item_id

    def _begin_rename(self):
        if self._renaming:
            return
        self._renaming = True
        self._title_label.hide()
        edit = QLineEdit(self._title_label.text())
        edit.setStyleSheet("""
            QLineEdit { border: 1px solid #3498DB; border-radius: 4px;
                padding: 3px 6px; font-size: 13px; font-weight: bold; color: #2C3E50; }
        """)
        edit.selectAll()
        edit.setFocus()
        edit.returnPressed.connect(self._commit_rename)
        edit.editingFinished.connect(self._commit_rename)
        self._title_layout.insertWidget(0, edit)
        self._edit = edit

    def _commit_rename(self):
        if not self._renaming:
            return
        self._renaming = False
        new_title = self._edit.text().strip()
        old_title = self._title_label.text()
        if new_title and new_title != old_title:
            self._workspace.rename_item(self._item_id, new_title)
        else:
            self._workspace._render()

    def keyPressEvent(self, event):
        if self._renaming and event.key() == Qt.Key_Escape:
            self._renaming = False
            self._workspace._render()
            return
        super().keyPressEvent(event)

    # 单击 / 双击
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and not self._dragging and not self._suppress_release:
            self._click_timer.start(280)
        self._suppress_release = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._click_timer.stop()
            self._begin_rename()
        super().mouseDoubleClickEvent(event)

    # 拖拽发起
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._press_pos is not None
            and event.buttons() & Qt.LeftButton
            and not self._renaming
        ):
            dist = (event.position().toPoint() - self._press_pos).manhattanLength()
            if dist > 10:
                self._dragging = True
                self._suppress_release = True
                self._click_timer.stop()
                drag = QDrag(self)
                mime = QMimeData()
                mime.setData(MIME_ITEM, self._item_id.encode("utf-8"))
                drag.setMimeData(mime)
                drag.setPixmap(self.grab())
                drag.exec_(Qt.MoveAction)
                self._dragging = False
                self._press_pos = None
        super().mouseMoveEvent(event)

    # 右键菜单
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        status_menu = menu.addMenu("切换状态")
        for status in STATUSES:
            action = status_menu.addAction(status)
            action.setCheckable(True)
            action.setChecked(status == self._workspace._find_item(self._item_id).status)
            action.triggered.connect(lambda _=False, s=status: self._workspace.move_item(self._item_id, s))
        menu.addAction("编辑详情", lambda: self._workspace._open_detail(self._item_id))
        menu.addSeparator()
        menu.addAction("删除", lambda: self._workspace.delete_item(self._item_id))
        menu.exec_(event.globalPos())
