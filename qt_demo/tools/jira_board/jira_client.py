"""
Jira 客户端 - 复用 jira_weekly_report 的 Jira Cloud REST API v3 调用方式（仅标准库）
"""

import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

# 本地覆盖配置（可选，优先；cwd 下的 jira_config.json，已加入 .gitignore）
LOCAL_CONFIG = "jira_config.json"
# 主配置来源：jira_weekly_report 目录下的 config.json
WEEKLY_REPORT_CONFIG = r"D:\Work\4_脚本\jira_weekly_report\config.json"

FIELDS = ["summary", "status", "project", "updated", "assignee", "issuetype"]

# 不展示的“结束/旁路”状态（按包含匹配，忽略大小写）
EXCLUDED_STATUSES = {"已关闭", "待验证", "reject", "monitor", "已完成"}


def is_excluded_status(status: str) -> bool:
    norm = (status or "").lower()
    return any(token in norm for token in EXCLUDED_STATUSES)


def load_config() -> dict:
    """配置解析链：本地 jira_config.json → jira_weekly_report/config.json → 环境变量"""
    cfg = {}
    for source in (_local_config(), _weekly_config(), _env_config()):
        cfg.update({key: value for key, value in source.items() if value})
    return cfg


def _read_json_file(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): v for k, v in data.items()}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _local_config() -> dict:
    return _read_json_file(LOCAL_CONFIG)


def _weekly_config() -> dict:
    return _read_json_file(WEEKLY_REPORT_CONFIG)


def _env_config() -> dict:
    return {
        "jira_url": os.environ.get("JIRA_URL", "").strip(),
        "jira_username": os.environ.get("JIRA_USERNAME", "").strip(),
        "jira_api_token": os.environ.get("JIRA_API_TOKEN", "").strip(),
    }


def require_credentials(cfg: dict) -> None:
    missing = [
        key for key in ("jira_url", "jira_username", "jira_api_token")
        if not cfg.get(key)
    ]
    if missing:
        raise ValueError(
            "缺少配置：" + "、".join(missing)
            + "；请检查 jira_weekly_report/config.json 或设置环境变量"
        )


def build_jql() -> str:
    return "assignee = currentUser() ORDER BY updated DESC"


def post_json(url: str, payload: dict, headers: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Jira API {url} 请求失败 (HTTP {exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接 Jira：{exc}") from exc


def fetch_issues(cfg: dict, jql: str, limit: int = 500) -> list:
    base = cfg["jira_url"].rstrip("/") + "/rest/api/3/search/jql"
    auth = base64.b64encode(
        f"{cfg['jira_username']}:{cfg['jira_api_token']}".encode("utf-8")
    ).decode("ascii")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Basic {auth}",
    }
    issues = []
    next_token = None
    while True:
        remaining = max(1, limit - len(issues))
        payload = {
            "jql": jql,
            "maxResults": min(100, remaining),
            "fields": FIELDS,
        }
        if next_token:
            payload["nextPageToken"] = next_token
        data = post_json(base, payload, headers)
        issues.extend(data.get("issues", []) or [])
        next_token = data.get("nextPageToken") or None
        if not next_token or len(issues) >= limit:
            break
    return issues


def normalize_issue(issue: dict, base_url: str) -> dict:
    fields = issue.get("fields") or {}
    status = fields.get("status") or {}
    project = fields.get("project") or {}
    assignee = fields.get("assignee") or {}
    issuetype = fields.get("issuetype") or {}
    key = issue.get("key") or ""
    return {
        "key": key,
        "summary": (fields.get("summary") or "").strip(),
        "status": status.get("name") or "",
        "project": project.get("key") or "",
        "assignee": assignee.get("displayName") or assignee.get("emailAddress") or "",
        "issuetype": issuetype.get("name") or "",
        "updated": fields.get("updated") or "",
        "url": f"{base_url.rstrip('/')}/browse/{key}",
    }


def format_time(value: str) -> str:
    if not value:
        return ""
    text = value
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    text = text.replace("+0000", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return text[:10]
