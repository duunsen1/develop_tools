"""
工作区对话框：事项详情编辑 + 标签管理
"""

from collections import Counter

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QCheckBox, QPlainTextEdit, QPushButton, QListWidget,
    QListWidgetItem, QMessageBox, QWidget, QGroupBox, QLabel, QInputDialog,
)
from PySide6.QtCore import Qt

from .models import STATUSES, tag_color


DIALOG_STYLE = """
QDialog { background-color: #F5F6FA; }
QLabel { color: #2C3E50; }
QLineEdit, QPlainTextEdit, QComboBox {
    background-color: white; border: 1px solid #BDC3C7;
    border-radius: 4px; padding: 6px 8px; font-size: 13px;
}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
    border: 1px solid #3498DB;
}
QPushButton {
    background-color: #ECF0F1; border: 1px solid #BDC3C7;
    border-radius: 4px; padding: 6px 16px; font-size: 13px;
}
QPushButton:hover { background-color: #DFE6EA; }
QPushButton#primary { background-color: #3498DB; color: white; border: none; }
QPushButton#primary:hover { background-color: #2980B9; }
QPushButton#danger { background-color: #E74C3C; color: white; border: none; }
QPushButton#danger:hover { background-color: #C0392B; }
"""


class ItemDialog(QDialog):
    """事项详情编辑：主题 / 状态 / 标签 / 长文本备注"""

    def __init__(self, tags, item=None, parent=None):
        super().__init__(parent)
        self._all_tags = list(tags)
        self._item = item
        self.setWindowTitle("编辑详情" if item else "新增事项")
        self.setMinimumSize(480, 420)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("输入事项主题")
        form.addRow("主题:", self._title_edit)

        self._status_combo = QComboBox()
        for s in STATUSES:
            self._status_combo.addItem(s)
        form.addRow("状态:", self._status_combo)

        layout.addLayout(form)

        # 标签勾选
        tag_group = QGroupBox("标签")
        tag_group.setStyleSheet("QGroupBox { font-size: 13px; color: #7F8C8D; font-weight: bold; }")
        tag_layout = QVBoxLayout(tag_group)
        tag_layout.setSpacing(6)
        self._tag_checks = []
        if self._all_tags:
            for tag in self._all_tags:
                cb = QCheckBox(tag)
                cb.setStyleSheet("font-size: 13px; color: #2C3E50;")
                self._tag_checks.append(cb)
                tag_layout.addWidget(cb)
        else:
            hint = QLabel("暂无标签，可先到「管理标签」中添加")
            hint.setStyleSheet("font-size: 12px; color: #95A5A6;")
            tag_layout.addWidget(hint)
        tag_layout.addStretch()
        layout.addWidget(tag_group, 1)

        # 详情备注
        detail_label = QLabel("详情备注")
        detail_label.setStyleSheet("font-size: 13px; color: #7F8C8D; font-weight: bold;")
        layout.addWidget(detail_label)
        self._detail_edit = QPlainTextEdit()
        self._detail_edit.setPlaceholderText("记录详细说明、进度、链接等…")
        layout.addWidget(self._detail_edit, 2)

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        ok = QPushButton("保存")
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.clicked.connect(self._on_ok)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

    def _load_values(self):
        if not self._item:
            return
        self._title_edit.setText(self._item.title)
        self._status_combo.setCurrentText(self._item.status)
        selected = set(self._item.tags)
        for cb in self._tag_checks:
            cb.setChecked(cb.text() in selected)
        self._detail_edit.setPlainText(self._item.detail)

    def _on_ok(self):
        if not self._title_edit.text().strip():
            QMessageBox.warning(self, "提示", "主题不能为空")
            self._title_edit.setFocus()
            return
        self.accept()

    def result_fields(self):
        """返回 (title, status, tags, detail)"""
        title = self._title_edit.text().strip()
        status = self._status_combo.currentText()
        tags = [cb.text() for cb in self._tag_checks if cb.isChecked()]
        detail = self._detail_edit.toPlainText()
        return title, status, tags, detail


class TagManagerDialog(QDialog):
    """标签管理：新增 / 重命名 / 删除，删除时同步从所有事项移除"""

    def __init__(self, tags, items, parent=None):
        super().__init__(parent)
        self._tags = list(tags)
        self._counts = Counter(t for item in items for t in item.tags)
        self._renamed = {}
        self.setWindowTitle("管理标签")
        self.setMinimumSize(380, 420)
        self.setStyleSheet(DIALOG_STYLE)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget { background-color: white; border: 1px solid #BDC3C7;
                border-radius: 4px; font-size: 13px; }
            QListWidget::item { padding: 8px 10px; }
            QListWidget::item:selected { background-color: #D6EAF8; color: #2C3E50; }
        """)
        layout.addWidget(self._list, 1)
        self._refresh()

        btn_row = QHBoxLayout()
        add = QPushButton("＋ 新增")
        add.clicked.connect(self._add_tag)
        rename = QPushButton("重命名")
        rename.clicked.connect(self._rename_tag)
        delete = QPushButton("删除")
        delete.setObjectName("danger")
        delete.clicked.connect(self._delete_tag)
        btn_row.addWidget(add)
        btn_row.addWidget(rename)
        btn_row.addWidget(delete)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        ok = QPushButton("完成")
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        bottom_row.addWidget(ok)
        layout.addLayout(bottom_row)

    def _refresh(self):
        self._list.clear()
        for tag in self._tags:
            count = self._counts.get(tag, 0)
            item = QListWidgetItem(f"{tag}  （{count} 个事项）")
            item.setData(Qt.UserRole, tag)
            self._list.addItem(item)

    def _current_tag(self):
        row = self._list.currentRow()
        if row < 0:
            return None
        return self._list.item(row).data(Qt.UserRole)

    def _add_tag(self):
        name, ok = QInputDialog.getText(self, "新增标签", "标签名称:")
        name = name.strip()
        if not ok or not name:
            return
        if name in self._tags:
            QMessageBox.information(self, "提示", "标签已存在")
            return
        self._tags.append(name)
        self._refresh()

    def _rename_tag(self):
        old = self._current_tag()
        if not old:
            return
        new, ok = QInputDialog.getText(self, "重命名标签", "新名称:", text=old)
        new = new.strip()
        if not ok or not new or new == old:
            return
        if new in self._tags:
            QMessageBox.information(self, "提示", "标签已存在")
            return
        idx = self._tags.index(old)
        self._tags[idx] = new
        self._counts[new] = self._counts.pop(old, 0)
        # 记录旧名->新名，供工作区同步更新事项中的标签
        for k, v in list(self._renamed.items()):
            if v == old:
                self._renamed[k] = new
        self._renamed[old] = new
        self._refresh()

    def _delete_tag(self):
        tag = self._current_tag()
        if not tag:
            return
        ret = QMessageBox.question(
            self, "删除标签",
            f"确定删除标签「{tag}」？\n该标签会从所有事项中移除，此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        self._tags.remove(tag)
        self._counts.pop(tag, None)
        self._refresh()

    def get_tags(self):
        return list(self._tags)

    def get_renames(self):
        return dict(self._renamed)
