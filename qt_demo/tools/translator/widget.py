"""
英中互译工具 - 调用公司 LLM API 进行翻译
"""

import json
import logging
import os
import tempfile
import urllib.error
import urllib.request

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QPlainTextEdit,
    QGroupBox, QDialog, QLineEdit, QFormLayout, QDialogButtonBox,
    QMessageBox, QComboBox,
)

from ...base_tool_widget import BaseToolWidget
from ...data_dir import data_dir

logger = logging.getLogger("devtools")

CONFIG_FILE = os.path.join(data_dir(), "translator_config.json")

# 默认 API 地址（空字符串表示未配置）
DEFAULT_API_URL = ""

# 公司 LLM 平台允许访问的对话模型（embedding/asr 模型不适用于翻译，未列入）
AVAILABLE_MODELS = [
    "qwen3.8-max-bailian",
    "qwen3.8-27b",
    "deepseek-v4-pro-bailian",
    "qwen3.7-flash-bailian",
    "deepseek-v4-flash-bailian",
    "qwen-long-bailian",
    "qwen3-vl-30b",
    "orith-1.5-35b",
]
DEFAULT_MODEL = AVAILABLE_MODELS[0]


# ===== 配置管理 =====

def load_config() -> dict:
    """从 %APPDATA%/DevTools/translator_config.json 加载配置"""
    if not os.path.exists(CONFIG_FILE):
        return {"api_url": "", "api_key": "", "model": ""}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "api_url": str(data.get("api_url", "")).strip(),
            "api_key": str(data.get("api_key", "")).strip(),
            "model": str(data.get("model", "")).strip(),
        }
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("翻译配置加载失败: %s", exc)
        return {"api_url": "", "api_key": "", "model": ""}


def save_config(api_url: str, api_key: str, model: str = "") -> None:
    """原子写入配置到 %APPDATA%/DevTools/translator_config.json"""
    payload = {"api_url": api_url.strip(), "api_key": api_key.strip(), "model": model.strip()}
    fd, tmp_path = tempfile.mkstemp(dir=data_dir(), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, CONFIG_FILE)
    except OSError:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def config_is_valid(cfg: dict) -> bool:
    return bool(cfg.get("api_url")) and bool(cfg.get("api_key")) and bool(cfg.get("model"))


# ===== 翻译工作线程 =====

class TranslateWorker(QThread):
    """后台调用 LLM API 翻译，不阻塞 UI"""

    result = Signal(str)       # 翻译结果
    error = Signal(str)        # 错误信息

    def __init__(self, api_url: str, api_key: str, model: str, text: str,
                 source_lang: str, target_lang: str, parent=None):
        super().__init__(parent)
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._text = text
        self._source = source_lang
        self._target = target_lang

    def run(self):
        try:
            translated = self._call_api()
            self.result.emit(translated)
        except Exception as exc:
            self.error.emit(str(exc))

    def _call_api(self) -> str:
        url = f"{self._api_url}/chat/completions"
        system_prompt = (
            f"Translate the following {self._source} text to {self._target}. "
            f"Return only the translation, no explanation."
        )
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self._text},
            ],
            "temperature": 0.1,
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
                resp_data = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            hint = ""
            if exc.code == 403 and "model" in detail:
                hint = "\n提示：模型无访问权限，请在设置中更换为团队允许的模型"
            raise RuntimeError(f"API 请求失败 (HTTP {exc.code}): {detail}{hint}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"无法连接 LLM 服务：{exc.reason}") from exc

        choices = resp_data.get("choices", [])
        if not choices:
            raise RuntimeError("API 返回内容为空，请检查模型名称是否正确")
        return choices[0].get("message", {}).get("content", "").strip()


# ===== 设置对话框 =====

class SettingsDialog(QDialog):
    """API 地址和 Key 配置对话框"""

    def __init__(self, current_cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("翻译设置")
        self.setMinimumWidth(500)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        form = QFormLayout()
        form.setSpacing(10)

        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("https://your-company-llm.example.com/v1")
        self._url_input.setText(current_cfg.get("api_url", ""))
        form.addRow("API 地址：", self._url_input)

        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("sk-...")
        self._key_input.setEchoMode(QLineEdit.Password)
        self._key_input.setText(current_cfg.get("api_key", ""))
        form.addRow("API Key：", self._key_input)

        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.addItems(AVAILABLE_MODELS)
        saved_model = current_cfg.get("model", "")
        if saved_model:
            idx = self._model_combo.findText(saved_model)
            if idx >= 0:
                self._model_combo.setCurrentIndex(idx)
            else:
                self._model_combo.setCurrentText(saved_model)
        else:
            self._model_combo.setCurrentText(DEFAULT_MODEL)
        form.addRow("模型：", self._model_combo)

        layout.addLayout(form)

        hint = QLabel("提示：API 地址需兼容 OpenAI Chat Completions 格式\n"
                       "即 POST {api_url}/chat/completions 返回标准 choices 结构\n"
                       "模型可从下拉框选择，也可手动输入平台允许的其他模型名")
        hint.setStyleSheet("color: #7F8C8D; font-size: 12px; padding: 4px 0;")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self):
        url = self._url_input.text().strip()
        key = self._key_input.text().strip()
        model = self._model_combo.currentText().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请输入 API 地址")
            self._url_input.setFocus()
            return
        if not key:
            QMessageBox.warning(self, "提示", "请输入 API Key")
            self._key_input.setFocus()
            return
        if not model:
            QMessageBox.warning(self, "提示", "请选择或输入模型名称")
            self._model_combo.setFocus()
            return
        self.accept()

    def get_config(self) -> dict:
        return {
            "api_url": self._url_input.text().strip(),
            "api_key": self._key_input.text().strip(),
            "model": self._model_combo.currentText().strip(),
        }


# ===== 翻译工具 Widget =====

class TranslatorWidget(BaseToolWidget):
    """英中互译工具"""

    LANGUAGES = {
        "en": "英语",
        "zh": "中文",
    }

    def tool_name(self) -> str:
        return "英中翻译"

    def tool_tip(self) -> str:
        return "调用公司 LLM 进行英中互译，需先配置 API 地址和 Key"

    def _setup_ui(self):
        # 加载配置
        self._cfg = load_config()
        self._direction = "en2zh"  # en2zh / zh2en

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # ── 标题 ──
        title = QLabel("英中互译")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #2C3E50;")
        layout.addWidget(title)

        # ── 工具条：方向切换 + 设置 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._btn_en2zh = QPushButton("EN → ZH")
        self._btn_en2zh.setCheckable(True)
        self._btn_en2zh.setChecked(True)
        self._btn_en2zh.clicked.connect(lambda: self._set_direction("en2zh"))
        self._btn_en2zh.setStyleSheet(self._toggle_style(True))
        toolbar.addWidget(self._btn_en2zh)

        self._btn_zh2en = QPushButton("ZH → EN")
        self._btn_zh2en.setCheckable(True)
        self._btn_zh2en.clicked.connect(lambda: self._set_direction("zh2en"))
        self._btn_zh2en.setStyleSheet(self._toggle_style(False))
        toolbar.addWidget(self._btn_zh2en)

        toolbar.addStretch()

        self._btn_settings = QPushButton("⚙ 设置")
        self._btn_settings.setStyleSheet("""
            QPushButton { background-color: #95A5A6; color: white; border: none;
                border-radius: 4px; padding: 7px 16px; font-size: 13px; }
            QPushButton:hover { background-color: #7F8C8D; }
        """)
        self._btn_settings.clicked.connect(self._open_settings)
        toolbar.addWidget(self._btn_settings)

        layout.addLayout(toolbar)

        # ── 输入区 ──
        input_group = QGroupBox("输入文本")
        input_layout = QVBoxLayout(input_group)
        input_layout.setContentsMargins(8, 8, 8, 8)

        self._input_text = QPlainTextEdit()
        self._input_text.setPlaceholderText("请输入要翻译的文本...")
        self._input_text.setMinimumHeight(120)
        self._input_text.setStyleSheet("""
            QPlainTextEdit {
                background-color: white; border: 1px solid #E0E4E8;
                border-radius: 6px; font-size: 14px; padding: 8px;
                font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            }
        """)
        input_layout.addWidget(self._input_text)
        layout.addWidget(input_group)

        # ── 操作按钮行 ──
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self._btn_translate = QPushButton("翻  译")
        self._btn_translate.setStyleSheet("""
            QPushButton { background-color: #3498DB; color: white; border: none;
                border-radius: 6px; padding: 10px 36px; font-size: 15px; font-weight: bold; }
            QPushButton:hover { background-color: #2980B9; }
            QPushButton:disabled { background-color: #BDC3C7; }
        """)
        self._btn_translate.clicked.connect(self._translate)
        action_row.addWidget(self._btn_translate)

        self._btn_clear = QPushButton("清空")
        self._btn_clear.setStyleSheet("""
            QPushButton { background-color: #ECF0F1; color: #2C3E50; border: 1px solid #BDC3C7;
                border-radius: 6px; padding: 10px 20px; font-size: 14px; }
            QPushButton:hover { background-color: #D5DBDB; }
        """)
        self._btn_clear.clicked.connect(self._clear_all)
        action_row.addWidget(self._btn_clear)

        action_row.addStretch()

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size: 13px; color: #7F8C8D;")
        action_row.addWidget(self._status_label)

        layout.addLayout(action_row)

        # ── 结果区 ──
        output_group = QGroupBox("翻译结果")
        output_layout = QVBoxLayout(output_group)
        output_layout.setContentsMargins(8, 8, 8, 8)

        self._result_text = QPlainTextEdit()
        self._result_text.setReadOnly(True)
        self._result_text.setMinimumHeight(120)
        self._result_text.setStyleSheet("""
            QPlainTextEdit {
                background-color: #F8F9FA; border: 1px solid #E0E4E8;
                border-radius: 6px; font-size: 14px; padding: 8px;
                font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
                color: #2C3E50;
            }
        """)
        output_layout.addWidget(self._result_text)
        layout.addWidget(output_group, 1)

        # ── 配置状态提示 ──
        if not config_is_valid(self._cfg):
            self._status_label.setText("⚠ 请先点击 ⚙ 设置 配置 API 地址、Key 和模型")
            self._btn_translate.setEnabled(False)

        self._main_layout.addLayout(layout)

        # 工作线程引用
        self._worker = None

    # ===== UI 辅助 =====

    def _toggle_style(self, active: bool) -> str:
        if active:
            return """
                QPushButton { background-color: #2C3E50; color: white; border: none;
                    border-radius: 4px; padding: 7px 16px; font-size: 13px; font-weight: bold; }
                QPushButton:hover { background-color: #34495E; }
            """
        return """
            QPushButton { background-color: #ECF0F1; color: #2C3E50; border: 1px solid #BDC3C7;
                border-radius: 4px; padding: 7px 16px; font-size: 13px; }
            QPushButton:hover { background-color: #D5DBDB; }
        """

    def _set_direction(self, direction: str):
        self._direction = direction
        self._btn_en2zh.setChecked(direction == "en2zh")
        self._btn_zh2en.setChecked(direction == "zh2en")
        self._btn_en2zh.setStyleSheet(self._toggle_style(direction == "en2zh"))
        self._btn_zh2en.setStyleSheet(self._toggle_style(direction == "zh2en"))

    # ===== 动作 =====

    def _open_settings(self):
        dlg = SettingsDialog(self._cfg, self)
        if dlg.exec() == QDialog.Accepted:
            new_cfg = dlg.get_config()
            try:
                save_config(new_cfg["api_url"], new_cfg["api_key"], new_cfg["model"])
                self._cfg = new_cfg
                logger.info("翻译配置已保存")
                if config_is_valid(self._cfg):
                    self._btn_translate.setEnabled(True)
                    self._status_label.setText("配置已保存")
                else:
                    self._btn_translate.setEnabled(False)
                    self._status_label.setText("⚠ 配置不完整，请重新设置")
            except OSError as exc:
                QMessageBox.critical(self, "错误", f"配置保存失败：{exc}")
                self._status_label.setText("❌ 配置保存失败")

    def _clear_all(self):
        self._input_text.clear()
        self._result_text.clear()
        self._status_label.setText("")

    def _translate(self):
        text = self._input_text.toPlainText().strip()
        if not text:
            self._status_label.setText("请输入要翻译的文本")
            return
        if not config_is_valid(self._cfg):
            self._status_label.setText("⚠ 请先配置 API 地址和 Key")
            self._btn_translate.setEnabled(False)
            return

        if self._direction == "en2zh":
            source, target = "English", "Chinese"
        else:
            source, target = "Chinese", "English"

        # 禁用按钮，防止重复点击
        self._set_busy(True)
        self._result_text.clear()
        self._status_label.setText("正在翻译...")

        self._worker = TranslateWorker(
            self._cfg["api_url"], self._cfg["api_key"], self._cfg["model"],
            text, source, target, parent=self,
        )
        self._worker.result.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_result(self, translated: str):
        self._result_text.setPlainText(translated)
        self._status_label.setText("✅ 翻译完成")

    def _on_error(self, message: str):
        self._result_text.setPlainText("")
        self._status_label.setText(f"❌ 翻译失败")
        QMessageBox.warning(self, "翻译失败", message)
        logger.warning("翻译失败: %s", message)

    def _on_worker_finished(self):
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        self._set_busy(False)

    def _set_busy(self, busy: bool):
        self._btn_translate.setEnabled(not busy)
        self._btn_clear.setEnabled(not busy)
        self._btn_settings.setEnabled(not busy)
        self._btn_en2zh.setEnabled(not busy)
        self._btn_zh2en.setEnabled(not busy)

    def on_deactivate(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)