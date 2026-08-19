"""
常用指令工具 - 一键执行设备快捷操作与日志/构建导出
"""

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QTextEdit, QLineEdit, QFileDialog, QMessageBox,
    QProgressBar,
)

from ...base_tool_widget import BaseToolWidget
from ...win_proc import CREATE_NO_WINDOW


SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
PULL_LOG_PS1 = os.path.join(SCRIPTS_DIR, "pull-log.ps1")
PULL_BUILD_PS1 = os.path.join(SCRIPTS_DIR, "pull-build.ps1")
GETLOG_PY = os.path.join(SCRIPTS_DIR, "getlog.py")
DEFAULT_NT_LOG_DIR = r"E:\PowerShell"

# ===== 设备快捷操作命令 =====
CMD_OPEN_FP = "adb shell am start -n com.goodix.fingerprint.setting/.SPMT1Activity"
CMD_REBOOT_EDL = "adb reboot edl"
SKIP_SETUP_STEPS = [
    {"cmd": "adb root", "timeout": 30, "ignore_error": True},
    {"cmd": "adb shell pm disable com.android.setupwizard.overlay", "timeout": 30, "ignore_error": False},
    {"cmd": "adb shell settings put secure user_setup_complete 1", "timeout": 30, "ignore_error": False},
    {"cmd": "adb shell settings put global device_provisioned 1", "timeout": 30, "ignore_error": False},
    {"cmd": "adb reboot", "timeout": 15, "ignore_error": True},
]
NT_LOG_REMOTE = "/sdcard/Android/data/com.nothing.logkit/files/logs/"


class CommandWorker(QThread):
    """通用命令序列执行器"""
    output = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, steps, parent=None):
        super().__init__(parent)
        self._steps = steps
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        try:
            n = len(self._steps)
            for i, step in enumerate(self._steps, 1):
                if not self._running:
                    self.output.emit("已停止")
                    break
                cmd = step["cmd"]
                # 列表命令直接创建进程(不经 cmd.exe)，避免路径里的 & | ^ 等字符
                # 被当作 shell 命令分隔符拆成多条命令；字符串命令保持原有行为
                is_list = isinstance(cmd, (list, tuple))
                display = cmd if isinstance(cmd, str) else subprocess.list2cmdline(cmd)
                self.output.emit(f"[{i}/{n}] >>> {display}")
                try:
                    p = subprocess.run(
                        cmd, shell=not is_list, capture_output=True, text=True,
                        errors="replace", timeout=step.get("timeout", 30),
                        creationflags=CREATE_NO_WINDOW,
                    )
                    if p.stdout.strip():
                        self.output.emit(p.stdout.strip())
                    if p.stderr.strip():
                        self.output.emit(p.stderr.strip())
                    if p.returncode != 0:
                        if step.get("ignore_error", False):
                            self.output.emit(f"[WARN] exit={p.returncode} (已忽略): {display}")
                        else:
                            raise RuntimeError(f"命令失败 (exit={p.returncode}): {display}")
                except subprocess.TimeoutExpired:
                    if step.get("ignore_error", False):
                        self.output.emit(f"[WARN] 超时 (已忽略): {display}")
                    else:
                        raise RuntimeError(f"命令超时: {display}")
            self.finished.emit(True, "操作完成")
        except Exception as e:
            self.output.emit(f"ERROR: {e}")
            self.finished.emit(False, str(e))


def _ps1_cmd(script_path, source_path):
    # 返回命令列表，subprocess 直接创建进程，不经过 cmd.exe，
    # 避免路径中的 & | ^ 等字符被 shell 拆成多条命令
    return [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", script_path, "-Yes", "-NoOpen", source_path,
    ]


class QuickCmdsWidget(BaseToolWidget):
    """常用指令工具"""

    def tool_name(self) -> str:
        return "常用指令"

    def tool_tip(self) -> str:
        return "一键执行设备快捷操作与日志/构建导出"

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("常用指令")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #2C3E50;")
        layout.addWidget(title)

        self._btns = {}
        self._worker = None

        # 设备状态
        env_group = QGroupBox("设备状态")
        env_row = QHBoxLayout(env_group)
        self._env_label = QLabel("未检测")
        self._env_label.setStyleSheet("font-size: 13px;")
        env_row.addWidget(self._env_label)
        env_row.addStretch()
        btn_check = QPushButton("检测设备")
        btn_check.clicked.connect(self._check_env)
        env_row.addWidget(btn_check)
        layout.addWidget(env_group)

        # A 组：设备快捷操作
        dev_group = QGroupBox("设备快捷操作")
        dev_layout = QVBoxLayout(dev_group)
        dev_layout.setSpacing(8)

        btn_open_fp = QPushButton("打开指纹校准界面")
        btn_open_fp.setFixedWidth(160)
        btn_open_fp.setStyleSheet(self._btn_style("#27AE60", "#1E8449"))
        btn_open_fp.clicked.connect(self._run_open_fp)
        dev_layout.addLayout(self._op_row(btn_open_fp, "打开 Goodix 指纹校准 SPMT1Activity"))

        btn_reboot_edl = QPushButton("进到刷机模式 (EDL)")
        btn_reboot_edl.setFixedWidth(160)
        btn_reboot_edl.setStyleSheet(self._btn_style("#E67E22", "#CA6F1E"))
        btn_reboot_edl.clicked.connect(self._run_reboot_edl)
        dev_layout.addLayout(self._op_row(btn_reboot_edl, "adb reboot edl"))

        btn_skip_setup = QPushButton("跳过开机向导")
        btn_skip_setup.setFixedWidth(160)
        btn_skip_setup.setStyleSheet(self._btn_style("#E74C3C", "#C0392B"))
        btn_skip_setup.clicked.connect(self._run_skip_setup)
        dev_layout.addLayout(self._op_row(btn_skip_setup, "adb root + pm disable setupwizard + settings put ×2 + 重启"))

        self._btns["打开指纹校准界面"] = btn_open_fp
        self._btns["进到刷机模式 (EDL)"] = btn_reboot_edl
        self._btns["跳过开机向导"] = btn_skip_setup
        layout.addWidget(dev_group)

        # B 组：日志/构建导出
        exp_group = QGroupBox("日志 / 构建导出")
        exp_layout = QVBoxLayout(exp_group)
        exp_layout.setSpacing(8)

        # 共享 NT 日志保存目录
        nt_row = QHBoxLayout()
        nt_row.addWidget(self._label("NT 日志保存目录:"))
        self._nt_dir_input = QLineEdit(DEFAULT_NT_LOG_DIR)
        self._nt_dir_input.setPlaceholderText("本地保存目录")
        nt_row.addWidget(self._nt_dir_input, 1)
        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._browse_nt_dir)
        nt_row.addWidget(btn_browse)
        exp_layout.addLayout(nt_row)

        # 导出 testlog
        btn_pull_log = QPushButton("执行")
        btn_pull_log.setFixedWidth(120)
        btn_pull_log.clicked.connect(self._run_pull_log)
        self._testlog_input = QLineEdit()
        self._testlog_input.setPlaceholderText(r"\\172.30.1.96\testlog\Smartphone\Xian\23112C_17C\ARBOK17C-2322")
        exp_layout.addLayout(self._src_row("导出 testlog", self._testlog_input, btn_pull_log))

        # 导出构建版本
        btn_pull_build = QPushButton("执行")
        btn_pull_build.setFixedWidth(120)
        btn_pull_build.clicked.connect(self._run_pull_build)
        self._build_input = QLineEdit()
        self._build_input.setPlaceholderText(r"\\172.30.10.183\code\temp\24111C\24111C_5.0_master_20260702_145627_tp_test")
        exp_layout.addLayout(self._src_row("导出构建版本", self._build_input, btn_pull_build))

        # 导出 NT 日志
        btn_pull_nt = QPushButton("执行")
        btn_pull_nt.setFixedWidth(120)
        btn_pull_nt.clicked.connect(self._run_pull_nt)
        exp_layout.addLayout(self._plain_row("导出 NT 日志", "adb pull " + NT_LOG_REMOTE, btn_pull_nt))

        # 导出 NT 日志并解压
        btn_pull_nt_zip = QPushButton("执行")
        btn_pull_nt_zip.setFixedWidth(120)
        btn_pull_nt_zip.clicked.connect(self._run_pull_nt_zip)
        exp_layout.addLayout(self._plain_row("导出 NT 日志并解压", "pull 后 7z 自动解压", btn_pull_nt_zip))

        self._btns["导出 testlog"] = btn_pull_log
        self._btns["导出构建版本"] = btn_pull_build
        self._btns["导出 NT 日志"] = btn_pull_nt
        self._btns["导出 NT 日志并解压"] = btn_pull_nt_zip
        layout.addWidget(exp_group)

        # 进度条
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(4)
        self._progress.hide()
        layout.addWidget(self._progress)

        # 输出
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

    # ===== UI 辅助 =====

    @staticmethod
    def _btn_style(base, hover):
        return f"""
            QPushButton {{ background-color: {base}; color: white; padding: 8px 12px;
                border-radius: 6px; font-size: 13px; font-weight: bold; border: none; }}
            QPushButton:hover {{ background-color: {hover}; }}
            QPushButton:disabled {{ background-color: #BDC3C7; }}
        """

    @staticmethod
    def _label(text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 13px; color: #2C3E50;")
        return lbl

    def _op_row(self, btn, desc):
        row = QHBoxLayout()
        row.addWidget(btn)
        row.addWidget(self._label(desc), 1)
        return row

    def _src_row(self, name, line_edit, btn):
        row = QHBoxLayout()
        row.addWidget(self._label(name), 0)
        row.addWidget(line_edit, 1)
        row.addWidget(btn, 0)
        return row

    def _plain_row(self, name, desc, btn):
        row = QHBoxLayout()
        row.addWidget(self._label(name), 0)
        row.addWidget(self._label(desc), 1)
        row.addWidget(btn, 0)
        return row

    # ===== 动作 =====

    def _check_env(self):
        self._output.clear()
        try:
            p = subprocess.run("adb version", shell=True, capture_output=True, text=True, timeout=5, creationflags=CREATE_NO_WINDOW)
            self._env_label.setText("ADB 环境正常")
            self._env_label.setStyleSheet("font-size: 13px; color: green; font-weight: bold;")
            self._output.append(f">>> adb version\n{p.stdout.strip()}")
        except Exception as e:
            self._env_label.setText("ADB 环境异常")
            self._env_label.setStyleSheet("font-size: 13px; color: red; font-weight: bold;")
            self._output.append(f"ERROR: {e}")

    def _browse_nt_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择 NT 日志保存目录", self._nt_dir_input.text())
        if path:
            self._nt_dir_input.setText(path)

    def _start(self, label, steps):
        self._output.append(f"\n===== {label} =====")
        self._set_busy(True)
        self._worker = CommandWorker(steps)
        self._worker.output.connect(self._on_output)
        self._worker.finished.connect(lambda ok, msg: self._on_finished(ok, msg, label))
        self._worker.start()

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

    # 设备快捷操作

    def _run_open_fp(self):
        self._start("打开指纹校准界面", [{"cmd": CMD_OPEN_FP, "timeout": 15, "ignore_error": False}])

    def _run_reboot_edl(self):
        self._start("进到刷机模式 (EDL)", [{"cmd": CMD_REBOOT_EDL, "timeout": 15, "ignore_error": True}])

    def _run_skip_setup(self):
        self._start("跳过开机向导", list(SKIP_SETUP_STEPS))

    # 日志/构建导出

    def _run_pull_log(self):
        src = self._testlog_input.text().strip()
        if not src:
            QMessageBox.warning(self, "警告", "请输入 testlog 源路径")
            return
        if not os.path.isfile(PULL_LOG_PS1):
            QMessageBox.warning(self, "警告", f"脚本不存在: {PULL_LOG_PS1}")
            return
        self._start("导出 testlog", [{"cmd": _ps1_cmd(PULL_LOG_PS1, src), "timeout": 600, "ignore_error": False}])

    def _run_pull_build(self):
        src = self._build_input.text().strip()
        if not src:
            QMessageBox.warning(self, "警告", "请输入构建版本源路径")
            return
        if not os.path.isfile(PULL_BUILD_PS1):
            QMessageBox.warning(self, "警告", f"脚本不存在: {PULL_BUILD_PS1}")
            return
        self._start("导出构建版本", [{"cmd": _ps1_cmd(PULL_BUILD_PS1, src), "timeout": 600, "ignore_error": False}])

    def _nt_dir(self):
        target = self._nt_dir_input.text().strip() or DEFAULT_NT_LOG_DIR
        os.makedirs(target, exist_ok=True)
        return target

    def _run_pull_nt(self):
        target = self._nt_dir()
        arg = subprocess.list2cmdline([target])
        cmd = f"adb pull {NT_LOG_REMOTE} {arg}"
        self._start("导出 NT 日志", [{"cmd": cmd, "timeout": 600, "ignore_error": False}])

    def _run_pull_nt_zip(self):
        target = self._nt_dir()
        if not os.path.isfile(GETLOG_PY):
            QMessageBox.warning(self, "警告", f"脚本不存在: {GETLOG_PY}")
            return
        arg = subprocess.list2cmdline([target])
        cmd = f'python "{GETLOG_PY}" {arg}'
        self._start("导出 NT 日志并解压", [{"cmd": cmd, "timeout": 600, "ignore_error": False}])

    def on_deactivate(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(1000)
            self._set_busy(False)
