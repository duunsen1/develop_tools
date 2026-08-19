"""
Jira 我的单 - 按状态/项目查看个人 Jira 单，手动或每 30 分钟自动刷新
"""

import logging
from datetime import datetime

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QCheckBox, QComboBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView,
)
from PySide6.QtCore import Qt, QTimer, QUrl, QThread, Signal
from PySide6.QtGui import QDesktopServices, QFontMetrics

from ...base_tool_widget import BaseToolWidget
from .jira_client import (
    load_config, require_credentials, build_jql, fetch_issues, normalize_issue,
    is_excluded_status,
)

AUTO_REFRESH_MS = 30 * 60 * 1000
FETCH_LIMIT = 500

logger = logging.getLogger("devtools")


class FetchWorker(QThread):
    """后台线程拉取个人 Jira 单，避免阻塞界面"""

    loaded = Signal(list)
    error = Signal(str)

    def __init__(self, cfg: dict, jql: str, limit: int, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._jql = jql
        self._limit = limit

    def run(self):
        try:
            issues = fetch_issues(self._cfg, self._jql, self._limit)
            records = [normalize_issue(item, self._cfg["jira_url"]) for item in issues]
            self.loaded.emit(records)
        except Exception as exc:
            self.error.emit(str(exc))


class JiraBoardWidget(BaseToolWidget):
    """Jira 个人单看板工具"""

    def tool_name(self) -> str:
        return "jira清单"

    def tool_tip(self) -> str:
        return "按状态/项目查看个人 Jira 单，支持按工作类型过滤，可手动或每 30 分钟自动刷新"

    def _setup_ui(self):
        self._records = []
        self._worker = None
        self._loaded_once = False
        self._type_filter = ""
        self._last_refresh_time = ""

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 工具条
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        btn_refresh = QPushButton("刷新")
        btn_refresh.setStyleSheet("""
            QPushButton { background-color: #3498DB; color: white; border: none;
                border-radius: 4px; padding: 7px 20px; font-size: 13px; font-weight: bold; }
            QPushButton:hover { background-color: #2980B9; }
            QPushButton:disabled { background-color: #BDC3C7; }
        """)
        btn_refresh.clicked.connect(self.refresh)
        toolbar.addWidget(btn_refresh)

        self._auto_check = QCheckBox("每 30 分钟自动刷新")
        self._auto_check.setStyleSheet("font-size: 13px; color: #2C3E50;")
        self._auto_check.setChecked(True)
        self._auto_check.toggled.connect(self._on_auto_toggled)
        toolbar.addWidget(self._auto_check)

        lbl_type = QLabel("类型:")
        lbl_type.setStyleSheet("font-size: 13px; color: #7F8C8D;")
        toolbar.addWidget(lbl_type)

        self._type_combo = QComboBox()
        self._type_combo.setMinimumWidth(110)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        toolbar.addWidget(self._type_combo)

        toolbar.addStretch()

        self._info_label = QLabel("")
        self._info_label.setStyleSheet("font-size: 13px; color: #7F8C8D;")
        toolbar.addWidget(self._info_label)

        layout.addLayout(toolbar)

        # 单子树
        self._tree = QTreeWidget()
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["单号", "主题"])
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setAnimated(True)
        self._tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        self._tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self._tree.header().setStretchLastSection(False)
        self._tree.setStyleSheet("""
            QTreeWidget {
                background-color: white; border: 1px solid #E0E4E8;
                border-radius: 8px; font-size: 13px;
            }
            QTreeWidget::item { padding: 4px 2px; }
            QTreeWidget::item:selected { background-color: #D6EAF8; color: #2C3E50; }
            QTreeWidget::item:hover { background-color: #EBF5FB; }
        """)
        layout.addWidget(self._tree, 1)

        # 状态提示
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size: 12px; color: #7F8C8D;")
        layout.addWidget(self._status_label)

        self._main_layout.addLayout(layout)

        # 自动刷新定时器
        self._timer = QTimer(self)
        self._timer.setInterval(AUTO_REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        if self._auto_check.isChecked():
            self._timer.start()

        self.refresh()

    def on_activate(self):
        if not self._loaded_once:
            self.refresh()

    def _on_auto_toggled(self, checked):
        if checked:
            self._timer.start()
        else:
            self._timer.stop()

    # ---------- 数据刷新 ----------

    def refresh(self):
        if self._worker is not None and self._worker.isRunning():
            return
        try:
            cfg = load_config()
            require_credentials(cfg)
        except Exception as exc:
            self._status_label.setText(f"配置错误：{exc}")
            self._info_label.setText("刷新失败")
            return

        self._status_label.setText("正在刷新…")
        logger.info("jira 刷新开始")
        self._worker = FetchWorker(cfg, build_jql(), FETCH_LIMIT, parent=self)
        self._worker.loaded.connect(self._on_loaded)
        self._worker.error.connect(self._on_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_worker_finished(self):
        """线程结束后清理引用，避免下次刷新访问到已删除的 worker"""
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def _on_loaded(self, records):
        # 排除已关闭/待验证/reject/monitor/已完成 等状态
        self._records = [r for r in records if not is_excluded_status(r.get("status", ""))]
        self._loaded_once = True
        self._refresh_type_combo()
        now = datetime.now().strftime("%H:%M:%S")
        self._last_refresh_time = now
        self._render_tree(self._visible_records())
        self._update_count_label()
        self._status_label.setText("刷新完成")
        logger.info("jira 刷新完成: 原始 %d 单, 排除后 %d 单", len(records), len(self._records))

    def _on_failed(self, message):
        self._status_label.setText(f"刷新失败：{message}")
        logger.warning("jira 刷新失败: %s", message)

    # ---------- 工作类型过滤 ----------

    def _visible_records(self):
        if not self._type_filter:
            return self._records
        return [r for r in self._records if r.get("issuetype") == self._type_filter]

    def _refresh_type_combo(self):
        current = self._type_combo.currentData() or ""
        types = sorted({r.get("issuetype", "") for r in self._records if r.get("issuetype")})
        self._type_combo.blockSignals(True)
        self._type_combo.clear()
        self._type_combo.addItem("全部类型", "")
        for t in types:
            self._type_combo.addItem(t, t)
        if current in types:
            self._type_combo.setCurrentIndex(self._type_combo.findData(current))
        self._type_filter = self._type_combo.currentData() or ""
        self._type_combo.blockSignals(False)

    def _on_type_changed(self, _index):
        self._type_filter = self._type_combo.currentData() or ""
        self._render_tree(self._visible_records())
        self._update_count_label()

    def _update_count_label(self):
        self._info_label.setText(
            f"上次刷新 {self._last_refresh_time} · 共 {len(self._visible_records())} 单"
        )

    # ---------- 渲染 ----------

    def _render_tree(self, records):
        self._tree.clear()

        by_status = {}
        for record in records:
            by_status.setdefault(record["status"] or "无状态", []).append(record)

        for status, issues in sorted(
            by_status.items(), key=lambda kv: len(kv[1]), reverse=True
        ):
            st_item = QTreeWidgetItem([f"{status}  （{len(issues)}）", ""])
            st_item.setForeground(0, Qt.darkBlue)
            st_item.setFlags(st_item.flags() & ~Qt.ItemIsSelectable)

            by_project = {}
            for record in issues:
                by_project.setdefault(record["project"] or "未知项目", []).append(record)

            for project, p_issues in sorted(by_project.items()):
                p_item = QTreeWidgetItem([f"{project}  （{len(p_issues)}）", ""])
                p_item.setForeground(0, Qt.darkGray)
                p_item.setFlags(p_item.flags() & ~Qt.ItemIsSelectable)

                for record in sorted(p_issues, key=lambda r: r["updated"], reverse=True):
                    # 单号只以软链接形式显示（item 文本留空，避免与链接叠影）
                    row = QTreeWidgetItem(["", record["summary"]])
                    p_item.addChild(row)
                    link = QLabel(
                        f'<a href="{record["url"]}" style="color:#2980B9; '
                        f'text-decoration:none;">{record["key"]}</a>'
                    )
                    link.setCursor(Qt.PointingHandCursor)
                    link.setStyleSheet("background: transparent; padding-left: 4px;")
                    link.linkActivated.connect(lambda url: QDesktopServices.openUrl(QUrl(url)))
                    self._tree.setItemWidget(row, 0, link)

                st_item.addChild(p_item)

            self._tree.addTopLevelItem(st_item)

        # 单号列宽按最长单号 + 展开箭头/缩进留白计算，让软链接完整显示
        max_key = max((r["key"] for r in records), key=len, default="")
        if max_key:
            fm = QFontMetrics(self._tree.font())
            self._tree.setColumnWidth(
                0, fm.horizontalAdvance(max_key) + 40 + self._tree.indentation() * 2
            )

        self._tree.expandAll()
