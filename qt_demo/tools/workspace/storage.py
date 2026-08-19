"""
工作区数据持久化
"""

import json
import os
import tempfile

from .models import Item

DATA_FILE = "workspace_data.json"


def load_data():
    """返回 (tags: list[str], items: list[Item])；文件缺失或损坏时返回空数据"""
    tags = []
    items = []
    if not os.path.exists(DATA_FILE):
        return tags, items
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw.get("tags"), list):
            tags = [t for t in raw["tags"] if isinstance(t, str)]
        if isinstance(raw.get("items"), list):
            items = [Item.from_dict(d) for d in raw["items"] if isinstance(d, dict)]
    except (json.JSONDecodeError, OSError):
        pass
    return tags, items


def save_data(tags, items):
    """写临时文件后原子替换，避免写入中断损坏数据"""
    payload = {
        "tags": list(tags),
        "items": [item.to_dict() for item in items],
    }
    fd, tmp_path = tempfile.mkstemp(dir=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, DATA_FILE)
    except OSError:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
