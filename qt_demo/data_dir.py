"""
应用数据目录 - 统一存放用户运行时数据

这些数据(历史记录/任务清单/Jira 配置)属于用户，必须放在与构建产物无关的
固定位置，避免打包重建或更换工作目录时丢失。此前用裸文件名写入当前工作目录，
导致 exe 运行时数据落在 dist\\DevTools\\ 里，每次重新打包都会被清除。
"""

import os

APP_DIR_NAME = "DevTools"


def data_dir() -> str:
    """返回应用数据目录(不存在则创建)。Windows 优先 %APPDATA%\\DevTools。"""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path
