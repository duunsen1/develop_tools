"""
工作区数据模型
"""

import time
import uuid
from dataclasses import dataclass, field

STATUSES = ["未开始", "正在进行", "已完成", "归档"]

STATUS_COLORS = {
    "未开始": "#95A5A6",
    "正在进行": "#3498DB",
    "已完成": "#27AE60",
    "归档": "#7F8C8D",
}

TAG_PALETTE = [
    "#E74C3C", "#E67E22", "#F1C40F", "#2ECC71",
    "#1ABC9C", "#3498DB", "#9B59B6", "#E91E63",
]


def tag_color(name: str) -> str:
    """按名称哈希从调色板稳定取色，同名标签颜色一致"""
    total = sum(ord(c) for c in name)
    return TAG_PALETTE[total % len(TAG_PALETTE)]


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Item:
    id: str
    title: str
    detail: str = ""
    status: str = STATUSES[0]
    tags: list = field(default_factory=list)
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "detail": self.detail,
            "status": self.status,
            "tags": list(self.tags),
            "created": self.created,
            "updated": self.updated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Item":
        item = cls(
            id=data.get("id", new_id()),
            title=data.get("title", ""),
            detail=data.get("detail", ""),
            status=data.get("status", STATUSES[0]),
            tags=list(data.get("tags", [])),
            created=data.get("created", time.time()),
            updated=data.get("updated", time.time()),
        )
        if item.status not in STATUSES:
            item.status = STATUSES[0]
        return item
