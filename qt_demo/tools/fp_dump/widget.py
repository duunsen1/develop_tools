"""
指纹 Dump 工具 - 开启/清除/导出指纹 fpdump 数据
对应 dump_path_fpdump 目录下的 4 个 bat 脚本，改为原生 adb 命令执行
"""

import os
import subprocess
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QTextEdit, QFileDialog, QMessageBox, QLineEdit,
    QProgressBar,
)
from PySide6.QtCore import Qt, Signal, QThread

from ...base_tool_widget import BaseToolWidget
from ...win_proc import CREATE_NO_WINDOW


# ===== 命令步骤定义 (对应原 bat 脚本) =====

def _enable_steps():
    """开启指纹 dump"""
    return [
        {"cmd": ["adb", "wait-for-device", "root"], "timeout": 60, "desc": "adb root"},
        {"cmd": ["adb", "wait-for-device", "shell", "setenforce", "0"], "timeout": 30, "desc": "adb shell setenforce 0"},
        {"cmd": ["adb", "wait-for-device", "shell", "setprop", "persist.vendor.goodix.dump_data", "1"], "timeout": 30, "desc": "adb shell setprop persist.vendor.goodix.dump_data 1"},
        {"cmd": ["adb", "wait-for-device", "shell", "setprop", "gf.debug.dump_data", "1"], "timeout": 30, "desc": "adb shell setprop gf.debug.dump_data 1"},
    ]


def _clear_all_steps():
    """清除全部指纹 dump 数据"""
    return [
        {"cmd": ["adb", "wait-for-device", "root"], "timeout": 60, "desc": "adb root"},
        {"cmd": ["adb", "wait-for-device", "shell", "rm", "-rf", "/data/vendor/fpdump/*"], "timeout": 30, "desc": "adb shell rm -rf /data/vendor/fpdump/*"},
    ]


def _clear_unlock_steps():
    """仅清除解锁指纹 dump 数据"""
    return [
        {"cmd": ["adb", "wait-for-device", "root"], "timeout": 60, "desc": "adb root"},
        {"cmd": ["adb", "wait-for-device", "shell", "rm", "-rf", "/data/vendor/fpdump/gfp/0/3020511/auth/*"], "timeout": 30, "desc": "adb shell rm -rf /data/vendor/fpdump/gfp/0/3020511/auth/*"},
    ]


def _pull_steps(target_dir: str):
    """导出指纹 dump 数据到本地目录 (fpdump / goodix 按项目二选一，存在才拉取)"""
    steps = [
        {"cmd": ["adb", "wait-for-device", "root"], "timeout": 60, "desc": "adb root"},
    ]
    for remote in ("/data/vendor/fpdump", "/data/vendor/goodix"):
        steps.append({
            "cmd": ["adb", "wait-for-device", "shell", "test", "-e", remote],
            "timeout": 30,
            "desc": f"检查设备端 {remote} 是否存在",
            "check_only": True,
        })
        steps.append({
            "cmd": ["adb", "wait-for-device", "pull", f"{remote}/", target_dir],
            "timeout": 120,
            "desc": f"adb pull {remote}/ -> {target_dir}",
            "optional": True,
        })
    return steps


class DumpWorker(QThread):
    """后台执行 adb 命令序列，避免 UI 卡死"""

    output = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, steps, parent=None):
        super().__init__(parent)
        self._steps = steps

    def run(self):
        skip_next = False
        try:
            for step in self._steps:
                cmd = step["cmd"]
                if step.get("optional") and skip_next:
                    self.output.emit(f"跳过: 设备端不存在 -> {step.get('desc', ' '.join(cmd))}")
                    skip_next = False
                    continue
                self.output.emit(f">>> {step.get('desc', ' '.join(cmd))}")
                try:
                    p = subprocess.run(
                        cmd, capture_output=True, text=True,
                        errors="replace", timeout=step.get("timeout", 30),
                        creationflags=CREATE_NO_WINDOW,
                    )
                except subprocess.TimeoutExpired:
                    raise RuntimeError(f"命令超时: {' '.join(cmd)}")
                if p.stdout.strip():
                    self.output.emit(p.stdout.strip())
                if p.stderr.strip():
                    self.output.emit(p.stderr.strip())
                if p.returncode != 0:
                    if step.get("check_only"):
                        self.output.emit("⚠ 该路径不存在，跳过对应拉取")
                        skip_next = True
                        continue
                    raise RuntimeError(f"命令失败 (exit={p.returncode}): {' '.join(cmd)}")
                skip_next = False
            self.finished.emit(True, "操作完成")
        except Exception as e:
            self.output.emit(f"ERROR: {e}")
            self.finished.emit(False, str(e))


class FpDumpWidget(BaseToolWidget):
    """指纹 Dump 工具"""

    def tool_name(self) -> str:
        return "指纹 Dump"

    def tool_tip(self) -> str:
        return "开启/清除/导出指纹 fpdump 数据"

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("指纹 Dump 工具")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #2C3E50;")
        layout.addWidget(title)

        desc = QLabel("开启 Goodix 指纹 dump、清除 dump 数据、导出 dump 到本地")
        desc.setStyleSheet("font-size: 13px; color: #7F8C8D;")
        layout.addWidget(desc)

        # ---- 设备状态 ----
        env_group = QGroupBox("设备状态")
        env_row = QHBoxLayout(env_group)
        self._dev_label = QLabel("未检测")
        self._dev_label.setStyleSheet("font-size: 13px;")
        env_row.addWidget(self._dev_label)
        env_row.addStretch()
        btn_check = QPushButton("检测设备")
        btn_check.clicked.connect(self._check_device)
        env_row.addWidget(btn_check)
        layout.addWidget(env_group)

        # ---- 操作按钮 ----
        op_group = QGroupBox("操作")
        op_layout = QVBoxLayout(op_group)
        op_layout.setSpacing(8)

        self._btns = {}

        btn_enable = QPushButton("开启指纹 Dump")
        btn_enable.setToolTip("adb root + setenforce 0 + 两个 setprop dump_data 1")
        btn_enable.clicked.connect(lambda: self._run("开启指纹 Dump", _enable_steps()))
        self._style_button(btn_enable, "#27AE60", "#219A52")
        op_layout.addLayout(self._btn_row(btn_enable))

        btn_clear_all = QPushButton("清除全部 Dump 数据")
        btn_clear_all.setToolTip("rm -rf /data/vendor/fpdump/*")
        btn_clear_all.clicked.connect(lambda: self._run("清除全部 Dump 数据", _clear_all_steps()))
        self._style_button(btn_clear_all, "#E67E22", "#CA6F1E")
        op_layout.addLayout(self._btn_row(btn_clear_all))

        btn_clear_unlock = QPushButton("清除解锁 Dump 数据")
        btn_clear_unlock.setToolTip("rm -rf /data/vendor/fpdump/gfp/0/3020511/auth/*")
        btn_clear_unlock.clicked.connect(lambda: self._run("清除解锁 Dump 数据", _clear_unlock_steps()))
        self._style_button(btn_clear_unlock, "#E74C3C", "#C0392B")
        op_layout.addLayout(self._btn_row(btn_clear_unlock))

        btn_pull = QPushButton("导出 Dump 数据")
        btn_pull.setToolTip("adb pull /data/vendor/fpdump/ 和 /data/vendor/goodix/ 到本地")
        btn_pull.clicked.connect(self._on_pull)
        self._style_button(btn_pull, "#3498DB", "#2980B9")
        op_layout.addLayout(self._btn_row(btn_pull))

        self._btns = {
            "开启指纹 Dump": btn_enable,
            "清除全部 Dump 数据": btn_clear_all,
            "清除解锁 Dump 数据": btn_clear_unlock,
            "导出 Dump 数据": btn_pull,
        }
        layout.addWidget(op_group)

        # ---- 导出目录 ----
        pull_group = QGroupBox("导出目录")
        pull_row = QHBoxLayout(pull_group)
        pull_row.addWidget(QLabel("保存位置:"))
        self._target_input = QLineEdit(os.path.join(os.path.expanduser("~"), "fp_dump"))
        pull_row.addWidget(self._target_input, 1)
        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._browse_target)
        pull_row.addWidget(btn_browse)
        layout.addWidget(pull_group)

        # ---- 进度条 ----
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(4)
        self._progress.hide()
        layout.addWidget(self._progress)

        # ---- 输出 ----
        output_group = QGroupBox("操作输出")
        output_layout = QVBoxLayout(output_group)
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setStyleSheet("""
            QTextEdit { background-color: #1E1E1E; color: #D4D4D4; font-family: Consolas;
                font-size: 13px; border: 1px solid #333; border-radius: 4px; padding: 8px; }
        """)
        output_layout.addWidget(self._output)
        layout.addWidget(output_group, 1)

        self._main_layout.addLayout(layout)

        self._worker = None

    # ===== UI 辅助 =====

    @staticmethod
    def _style_button(btn, base, hover):
        btn.setStyleSheet(f"""
            QPushButton {{ background-color: {base}; color: white; padding: 8px 12px;
                border-radius: 6px; font-size: 13px; font-weight: bold; border: none; }}
            QPushButton:hover {{ background-color: {hover}; }}
            QPushButton:disabled {{ background-color: #BDC3C7; }}
        """)

    def _btn_row(self, btn):
        row = QHBoxLayout()
        btn.setFixedWidth(180)
        row.addWidget(btn)
        row.addStretch()
        return row

    # ===== 动作 =====

    def _check_device(self):
        self._output.clear()
        try:
            p = subprocess.run("adb devices", shell=True, capture_output=True, text=True,
                               timeout=5, creationflags=CREATE_NO_WINDOW)
            self._output.append(f">>> adb devices\n{p.stdout}")
            lines = [l for l in p.stdout.splitlines()[1:] if l.strip() and "\tdevice" in l]
            if lines:
                self._dev_label.setText(f"已连接 {len(lines)} 台设备")
                self._dev_label.setStyleSheet("font-size: 13px; color: green; font-weight: bold;")
            else:
                self._dev_label.setText("未检测到设备")
                self._dev_label.setStyleSheet("font-size: 13px; color: red; font-weight: bold;")
        except Exception as e:
            self._dev_label.setText("ADB 不可用")
            self._dev_label.setStyleSheet("font-size: 13px; color: red; font-weight: bold;")
            self._output.append(f"ERROR: {e}")

    def _browse_target(self):
        path = QFileDialog.getExistingDirectory(self, "选择导出目录", self._target_input.text())
        if path:
            self._target_input.setText(path)

    def _run(self, label, steps):
        self._output.append(f"\n===== {label} =====")
        self._set_busy(True)
        self._worker = DumpWorker(steps)
        self._worker.output.connect(self._on_output)
        self._worker.finished.connect(lambda ok, msg: self._on_finished(ok, msg, label))
        self._worker.start()

    def _on_pull(self):
        base = self._target_input.text().strip()
        if not base:
            QMessageBox.warning(self, "提示", "请先设置导出目录")
            return
        os.makedirs(base, exist_ok=True)
        # 每次导出使用独立的时间戳子目录，避免与历史/损坏残留目录冲突
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = os.path.join(base, f"fp_dump_{ts}")
        os.makedirs(target, exist_ok=True)
        self._output.append(f"导出目录: {target}")
        self._run("导出 Dump 数据", _pull_steps(target))

    def _set_busy(self, busy):
        for btn in self._btns.values():
            btn.setEnabled(not busy)
        self._progress.setVisible(busy)

    def _on_output(self, text):
        self._output.append(text)

    def _on_finished(self, ok, msg, label):
        self._set_busy(False)
        if ok:
            self._output.append(f"\n✅ {msg}")
        else:
            self._output.append(f"\nFAILED: {msg}")
            QMessageBox.critical(self, "错误", f"{label} 失败: {msg}")

    def on_deactivate(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(1000)
